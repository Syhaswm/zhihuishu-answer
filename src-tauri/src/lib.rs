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

fn bundled_root() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let dir = exe.parent()?;
    let python = dir.join("runtime").join("python.exe");
    let app = dir.join("server").join("app.py");
    if python.is_file() && app.is_file() {
        Some(dir.to_path_buf())
    } else {
        None
    }
}

fn app_root() -> PathBuf {
    if let Some(root) = bundled_root() {
        return root;
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..")
}

fn python_executable(root: &std::path::Path) -> PathBuf {
    let bundled = root.join("runtime").join("python.exe");
    if bundled.is_file() {
        return bundled;
    }
    let configured = PathBuf::from(r"D:\anaconda_conda\envs\full-stack\python.exe");
    if configured.is_file() {
        return configured;
    }
    PathBuf::from("python")
}

fn stop_stale_api() {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let script = "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -like '*server.app:app*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }";
        let _ = Command::new("powershell")
            .args(["-NoProfile", "-Command", script])
            .creation_flags(0x08000000)
            .output();
    }
}

fn start_api(token: &str) -> Option<Child> {
    stop_stale_api();
    let root = app_root();
    let mut command = Command::new(python_executable(&root));
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
        .env("PYTHONNOUSERSITE", "1")
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .current_dir(&root);
    if let Ok(log) = std::fs::File::create(root.join("api.log")) {
        if let Ok(err_log) = log.try_clone() {
            use std::process::Stdio;
            command.stdout(Stdio::from(log)).stderr(Stdio::from(err_log));
        }
    }
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
