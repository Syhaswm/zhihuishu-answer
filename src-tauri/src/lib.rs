use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::Manager;

struct ApiProcess(Mutex<Option<Child>>);

fn python_executable() -> PathBuf {
    let configured = PathBuf::from(r"D:\anaconda_conda\envs\full-stack\python.exe");
    if configured.is_file() {
        return configured;
    }
    PathBuf::from("python")
}

fn start_api() -> Option<Child> {
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
        .current_dir(root);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    command.spawn().ok()
}

pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            app.manage(ApiProcess(Mutex::new(start_api())));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("启动窗口失败")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app.try_state::<ApiProcess>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(child) = guard.as_mut() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        });
}
