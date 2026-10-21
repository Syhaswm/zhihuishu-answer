use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::LogicalSize;
use tauri::Manager;
use tauri::PhysicalPosition;
use tauri::PhysicalSize;
use tauri::WebviewWindow;

struct AppSecrets {
    token: String,
    api: Mutex<Option<Child>>,
}

struct SavedWindow {
    x: i32,
    y: i32,
    width: u32,
    height: u32,
    maximized: bool,
    always_on_top: bool,
}

struct DockState {
    saved: Mutex<Option<SavedWindow>>,
    active: Mutex<bool>,
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

#[tauri::command]
fn app_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

fn capture_window(window: &WebviewWindow) -> Result<SavedWindow, String> {
    let maximized = window.is_maximized().map_err(|e| e.to_string())?;
    let always_on_top = window.is_always_on_top().map_err(|e| e.to_string())?;
    if maximized {
        return Ok(SavedWindow {
            x: 0,
            y: 0,
            width: 1080,
            height: 800,
            maximized: true,
            always_on_top,
        });
    }
    let pos = window.outer_position().map_err(|e| e.to_string())?;
    let size = window.outer_size().map_err(|e| e.to_string())?;
    Ok(SavedWindow {
        x: pos.x,
        y: pos.y,
        width: size.width,
        height: size.height,
        maximized: false,
        always_on_top,
    })
}

#[tauri::command]
fn dock_apply(
    window: WebviewWindow,
    state: tauri::State<DockState>,
    side: String,
    width: u32,
    always_on_top: bool,
) -> Result<(), String> {
    let side = side.to_lowercase();
    if side != "left" && side != "right" {
        return Err("side 只能是 left 或 right".into());
    }
    let width = width.clamp(280, 560);
    let mut active = state.active.lock().map_err(|_| "窗口状态被占用".to_string())?;
    if !*active {
        let saved = capture_window(&window)?;
        let mut guard = state.saved.lock().map_err(|_| "窗口状态被占用".to_string())?;
        *guard = Some(saved);
    }
    if window.is_maximized().map_err(|e| e.to_string())? {
        window.unmaximize().map_err(|e| e.to_string())?;
    }
    let monitor = window
        .current_monitor()
        .map_err(|e| e.to_string())?
        .ok_or("找不到当前显示器")?;
    let scale = monitor.scale_factor();
    let work = monitor.work_area();
    let physical_width = ((width as f64) * scale).round() as u32;
    let height = work.size.height;
    let y = work.position.y;
    let x = if side == "left" {
        work.position.x
    } else {
        work.position.x + work.size.width as i32 - physical_width as i32
    };
    window
        .set_min_size(Some(LogicalSize::new(280.0, 400.0)))
        .map_err(|e| e.to_string())?;
    window
        .set_size(PhysicalSize::new(physical_width, height))
        .map_err(|e| e.to_string())?;
    window
        .set_position(PhysicalPosition::new(x, y))
        .map_err(|e| e.to_string())?;
    window
        .set_always_on_top(always_on_top)
        .map_err(|e| e.to_string())?;
    *active = true;
    Ok(())
}

#[tauri::command]
fn dock_restore(window: WebviewWindow, state: tauri::State<DockState>) -> Result<(), String> {
    let mut active = state.active.lock().map_err(|_| "窗口状态被占用".to_string())?;
    if !*active {
        return Ok(());
    }
    let saved = {
        let mut guard = state.saved.lock().map_err(|_| "窗口状态被占用".to_string())?;
        guard.take()
    };
    window
        .set_always_on_top(false)
        .map_err(|e| e.to_string())?;
    window
        .set_min_size(Some(LogicalSize::new(880.0, 640.0)))
        .map_err(|e| e.to_string())?;
    if let Some(saved) = saved {
        window
            .set_always_on_top(saved.always_on_top)
            .map_err(|e| e.to_string())?;
        if saved.maximized {
            window.maximize().map_err(|e| e.to_string())?;
        } else {
            window
                .set_size(PhysicalSize::new(saved.width, saved.height))
                .map_err(|e| e.to_string())?;
            window
                .set_position(PhysicalPosition::new(saved.x, saved.y))
                .map_err(|e| e.to_string())?;
        }
    } else {
        window
            .set_size(PhysicalSize::new(1080, 800))
            .map_err(|e| e.to_string())?;
    }
    *active = false;
    Ok(())
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

fn dev_root() -> Option<PathBuf> {
    let mut dir = std::env::current_exe().ok()?.parent()?.to_path_buf();
    for _ in 0..6 {
        if dir.join("server").join("app.py").is_file() {
            return Some(dir);
        }
        if !dir.pop() {
            break;
        }
    }
    None
}

fn app_root() -> PathBuf {
    if let Some(root) = bundled_root() {
        return root;
    }
    if let Some(root) = dev_root() {
        return root;
    }
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

fn python_executable(root: &std::path::Path) -> PathBuf {
    let bundled = root.join("runtime").join("python.exe");
    if bundled.is_file() {
        return bundled;
    }
    if let Ok(text) = std::fs::read_to_string(root.join("dev-python.txt")) {
        let configured = PathBuf::from(text.trim());
        if configured.is_file() {
            return configured;
        }
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
        .manage(DockState {
            saved: Mutex::new(None),
            active: Mutex::new(false),
        })
        .invoke_handler(tauri::generate_handler![
            api_token,
            app_version,
            dock_apply,
            dock_restore
        ])
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
