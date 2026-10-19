use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::Manager;

struct AppSecrets {
    token: String,
    api: Mutex<Option<Child>>,
}

fn random_token() -> String {
    let mut bytes = [0u8; 32];
    getrandom::getrandom(&mut bytes).expect("无法生成访问口令");
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

#[tauri::command]
fn api_token(state: tauri::State<AppSecrets>) -> String {
    state.token.clone()
}

fn python_executable() -> PathBuf {
    let configured = PathBuf::from(r"D:\anaconda_conda\envs\full-stack\python.exe");
    if configured.is_file() {
        return configured;
    }
    PathBuf::from("python")
}

fn start_api(token: &str) -> Option<Child> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
    let mut command = Command::new(python_executable());
    command
        .args([
            "-m",
            "uvicorn",
            "server.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--log-level",
            "warning",
        ])
        .env("ZHS_API_TOKEN", token)
        .current_dir(root);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    command.spawn().ok()
}

pub fn run() {
    let token = random_token();
    tauri::Builder::default()
        .manage(AppSecrets {
            token: token.clone(),
            api: Mutex::new(start_api(&token)),
        })
        .invoke_handler(tauri::generate_handler![api_token])
        .setup(|_app| Ok(()))
        .build(tauri::generate_context!())
        .expect("启动窗口失败")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app.try_state::<AppSecrets>() {
                    if let Ok(mut guard) = state.api.lock() {
                        if let Some(child) = guard.as_mut() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        });
}
