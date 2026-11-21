// The VoiceTut Kaggle window. The Python package does the work: this shell starts it from the
// virtualenv installed next to this binary and passes its answers and output to the page.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use serde_json::Value;
use tauri::{AppHandle, Emitter, Manager, RunEvent, State};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

/// Used when the app starts with no PATH at all (a bare launcher environment).
const DEFAULT_PATH: &str = "/usr/local/bin:/usr/bin:/bin";
const AUDIO: &[&str] = &["ogg", "opus", "wav", "mp3", "flac", "m4a", "webm"];

/// The `vk` step running now. One at a time: the page disables its buttons meanwhile.
#[derive(Default)]
struct Running(Arc<Mutex<Option<Child>>>);

struct Python {
    python: PathBuf,
    bin: PathBuf,
}

/// The virtualenv next to this binary (install.sh puts it there), or VOICETUT_PYTHON when
/// running a development build against another environment.
fn python() -> Python {
    if let Some(path) = std::env::var_os("VOICETUT_PYTHON") {
        let python = PathBuf::from(path);
        let bin = python.parent().map(Path::to_path_buf).unwrap_or_default();
        return Python { python, bin };
    }
    let here = std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(Path::to_path_buf))
        .unwrap_or_default();
    if cfg!(windows) {
        let bin = here.join("venv").join("Scripts");
        Python { python: bin.join("python.exe"), bin }
    } else {
        let bin = here.join("venv").join("bin");
        Python { python: bin.join("python"), bin }
    }
}

/// A Python command with the environment a menu launch lacks: the venv's `kaggle` CLI and bin
/// folder first on PATH, unbuffered UTF-8 output so lines arrive as they are printed.
fn python_command(args: &[String]) -> (Command, PathBuf) {
    let py = python();
    let mut command = Command::new(&py.python);
    command.args(args);
    let kaggle = py.bin.join(if cfg!(windows) { "kaggle.exe" } else { "kaggle" });
    let path = std::env::var_os("PATH")
        .filter(|p| !p.is_empty())
        .unwrap_or_else(|| DEFAULT_PATH.into());
    let mut folders = vec![py.bin.clone()];
    folders.extend(std::env::split_paths(&path));
    let joined = std::env::join_paths(folders).unwrap_or(path);
    command
        .env("KAGGLE_CLI", kaggle)
        .env("PATH", joined)
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONIOENCODING", "utf-8");
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: no console flashing up
    }
    (command, py.python)
}

fn not_started(python: &Path, error: std::io::Error) -> String {
    format!(
        "could not start Python at {} ({error}). Run desktop/install.sh again.",
        python.display()
    )
}

/// `python -m voicetut_kaggle.desktop_api <args>`: one JSON answer.
#[tauri::command]
async fn api(args: Vec<String>, input: Option<String>) -> Result<Value, String> {
    tauri::async_runtime::spawn_blocking(move || run_api(args, input))
        .await
        .map_err(|e| e.to_string())?
}

fn run_api(args: Vec<String>, input: Option<String>) -> Result<Value, String> {
    let mut full = vec!["-m".to_string(), "voicetut_kaggle.desktop_api".to_string()];
    full.extend(args);
    let (mut command, python) = python_command(&full);
    command.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped());
    let mut child = command.spawn().map_err(|e| not_started(&python, e))?;
    if let Some(mut stdin) = child.stdin.take() {
        if let Some(text) = input {
            stdin.write_all(text.as_bytes()).map_err(|e| e.to_string())?;
        }
    } // stdin closes here
    let output = child.wait_with_output().map_err(|e| e.to_string())?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    let answer = stdout.lines().rev().find(|line| !line.trim().is_empty()).unwrap_or("");
    serde_json::from_str(answer).map_err(|_| {
        let stderr = String::from_utf8_lossy(&output.stderr);
        format!("unexpected answer from Python: {} {}", stdout.trim(), stderr.trim())
    })
}

/// `python -m voicetut_kaggle -c <folder>/voices.yaml <args>`. Every output line becomes a
/// "vk-log" event. Returns whether the step succeeded; Err("stopped") after stop_vk.
#[tauri::command]
async fn run_vk(
    app: AppHandle,
    running: State<'_, Running>,
    folder: String,
    args: Vec<String>,
) -> Result<bool, String> {
    let slot = running.0.clone();
    tauri::async_runtime::spawn_blocking(move || run_vk_blocking(app, slot, folder, args))
        .await
        .map_err(|e| e.to_string())?
}

fn run_vk_blocking(
    app: AppHandle,
    slot: Arc<Mutex<Option<Child>>>,
    folder: String,
    args: Vec<String>,
) -> Result<bool, String> {
    let config = Path::new(&folder).join("voices.yaml");
    let mut full = vec![
        "-m".to_string(),
        "voicetut_kaggle".to_string(),
        "-c".to_string(),
        config.to_string_lossy().into_owned(),
    ];
    full.extend(args);
    let (mut command, python) = python_command(&full);
    command
        .current_dir(&folder)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let readers = {
        let mut guard = slot.lock().map_err(|_| "the app is in a bad state; restart it")?;
        if guard.is_some() {
            return Err("another step is still running".into());
        }
        let mut child = command.spawn().map_err(|e| not_started(&python, e))?;
        let readers = vec![
            stream(app.clone(), child.stdout.take()),
            stream(app.clone(), child.stderr.take()),
        ];
        *guard = Some(child);
        readers
    };
    loop {
        {
            let mut guard = slot.lock().map_err(|_| "the app is in a bad state; restart it")?;
            let Some(child) = guard.as_mut() else {
                return Err("stopped".into()); // stop_vk took and killed it
            };
            match child.try_wait() {
                Ok(Some(status)) => {
                    *guard = None;
                    drop(guard);
                    readers.into_iter().flatten().for_each(|reader| {
                        let _ = reader.join();
                    });
                    return Ok(status.success());
                }
                Ok(None) => {}
                Err(e) => {
                    *guard = None;
                    return Err(e.to_string());
                }
            }
        }
        thread::sleep(Duration::from_millis(200));
    }
}

fn stream<R: Read + Send + 'static>(app: AppHandle, reader: Option<R>) -> Option<thread::JoinHandle<()>> {
    let reader = reader?;
    Some(thread::spawn(move || {
        for line in BufReader::new(reader).split(b'\n').map_while(Result::ok) {
            let text = String::from_utf8_lossy(&line).trim_end_matches('\r').to_string();
            let _ = app.emit("vk-log", text);
        }
    }))
}

fn stop(slot: &Mutex<Option<Child>>) {
    if let Ok(mut guard) = slot.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

/// Stops the running step. What already started on Kaggle keeps running there.
#[tauri::command]
fn stop_vk(running: State<'_, Running>) {
    stop(&running.0);
}

/// A folder, a voice clip, or any file (the Kaggle token). None when cancelled.
#[tauri::command]
async fn pick(app: AppHandle, kind: String) -> Option<String> {
    let dialog = app.dialog().file();
    let picked = match kind.as_str() {
        "folder" => dialog.blocking_pick_folder(),
        "clip" => dialog.add_filter("Audio", AUDIO).blocking_pick_file(),
        _ => dialog.blocking_pick_file(),
    };
    picked.map(|path| path.to_string())
}

/// Opens a file or folder with the system's default app (the listening page in the browser).
#[tauri::command]
fn open_path(app: AppHandle, path: String) -> Result<(), String> {
    app.opener().open_path(path, None::<&str>).map_err(|e| e.to_string())
}

/// The folder given on the command line, else ~/my-voices.
#[tauri::command]
fn start_folder(app: AppHandle) -> String {
    if let Some(folder) = std::env::args().nth(1).filter(|arg| Path::new(arg).is_dir()) {
        return folder;
    }
    app.path()
        .home_dir()
        .map(|home| home.join("my-voices").to_string_lossy().into_owned())
        .unwrap_or_default()
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(Running::default())
        .invoke_handler(tauri::generate_handler![api, run_vk, stop_vk, pick, open_path, start_folder])
        .build(tauri::generate_context!())
        .expect("VoiceTut Kaggle could not start")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                stop(&app.state::<Running>().0); // a watch left running would push nothing more
            }
        });
}
