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

struct PetState {
    visible: Mutex<bool>,
}

fn normalize_opacity(percent: u8) -> u8 {
    match percent {
        100 => 100,
        95 => 95,
        90 => 90,
        _ => 85,
    }
}

fn apply_window_opacity(window: &WebviewWindow, percent: u8) -> Result<(), String> {
    let percent = normalize_opacity(percent);
    #[cfg(windows)]
    {
        use windows::Win32::Foundation::COLORREF;
        use windows::Win32::UI::WindowsAndMessaging::{
            GetWindowLongPtrW, SetLayeredWindowAttributes, SetWindowLongPtrW, GWL_EXSTYLE,
            LWA_ALPHA, WS_EX_LAYERED,
        };
        let hwnd = window.hwnd().map_err(|e| e.to_string())?;
        let alpha = if percent >= 100 {
            255u8
        } else {
            ((percent as f32 / 100.0) * 255.0).round() as u8
        };
        unsafe {
            let ex = GetWindowLongPtrW(hwnd, GWL_EXSTYLE);
            SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED.0 as isize);
            SetLayeredWindowAttributes(hwnd, COLORREF(0), alpha, LWA_ALPHA)
                .map_err(|e| format!("设置透明度失败: {e}"))?;
        }
        Ok(())
    }
    #[cfg(not(windows))]
    {
        if percent < 100 {
            return Err("当前系统暂不支持窗口透明度".into());
        }
        Ok(())
    }
}

#[tauri::command]
fn set_window_opacity(window: WebviewWindow, opacity: u8) -> Result<(), String> {
    apply_window_opacity(&window, opacity)
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

fn apply_always_on_top(window: &WebviewWindow, enabled: bool) -> Result<(), String> {
    window
        .set_always_on_top(enabled)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn set_always_on_top(window: WebviewWindow, enabled: bool) -> Result<(), String> {
    apply_always_on_top(&window, enabled)
}

#[tauri::command]
fn dock_apply(
    window: WebviewWindow,
    state: tauri::State<DockState>,
    side: String,
    width: u32,
    always_on_top: bool,
    opacity: u8,
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
    apply_always_on_top(&window, always_on_top)?;
    apply_window_opacity(&window, opacity)?;
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
    apply_window_opacity(&window, 100)?;
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

fn park_pet(window: &WebviewWindow) -> Result<(), String> {
    let monitor = window
        .current_monitor()
        .map_err(|e| e.to_string())?
        .ok_or("找不到当前显示器")?;
    let scale = monitor.scale_factor();
    let work = monitor.work_area();
    let width = (96.0 * scale).round() as u32;
    let height = (120.0 * scale).round() as u32;
    let x = work.position.x + work.size.width as i32 - width as i32;
    let y = work.position.y + (72.0 * scale).round() as i32;
    window
        .set_size(PhysicalSize::new(width, height))
        .map_err(|e| e.to_string())?;
    window
        .set_position(PhysicalPosition::new(x, y))
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
fn show_main(app: tauri::AppHandle) -> Result<(), String> {
    let window = app.get_webview_window("main").ok_or("找不到主窗口")?;
    let _ = window.unminimize();
    window.show().map_err(|e| e.to_string())?;
    window.set_focus().map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
fn set_pet_visible(
    app: tauri::AppHandle,
    state: tauri::State<PetState>,
    visible: bool,
) -> Result<(), String> {
    if let Ok(mut guard) = state.visible.lock() {
        *guard = visible;
    }
    let Some(window) = app.get_webview_window("pet") else {
        return Ok(());
    };
    if visible {
        window.show().map_err(|e| e.to_string())
    } else {
        window.hide().map_err(|e| e.to_string())
    }
}

#[tauri::command]
fn quit_app(app: tauri::AppHandle) {
    app.exit(0);
}

fn create_pet(app: &tauri::AppHandle) -> Result<(), String> {
    if app.get_webview_window("pet").is_some() {
        return Ok(());
    }
    let browser_args =
        "--proxy-server=direct:// --proxy-bypass-list=<-loopback>;localhost;127.0.0.1;*.localhost";
    let window = tauri::WebviewWindowBuilder::new(
        app,
        "pet",
        tauri::WebviewUrl::App("index.html".into()),
    )
    .title("智慧树答题")
    .inner_size(96.0, 120.0)
    .resizable(false)
    .decorations(false)
    .transparent(true)
    .shadow(false)
    .always_on_top(true)
    .skip_taskbar(true)
    .focused(false)
    .visible(true)
    .additional_browser_args(browser_args)
    .initialization_script("window.__ZHS_PET__=true")
    .build()
    .map_err(|err| err.to_string())?;
    park_pet(&window)?;
    let visible = app
        .try_state::<PetState>()
        .and_then(|state| state.visible.lock().ok().map(|guard| *guard))
        .unwrap_or(true);
    if !visible {
        window.hide().map_err(|err| err.to_string())?;
    }
    Ok(())
}

fn schedule_pet(app: tauri::AppHandle) {
    std::thread::spawn(move || {
        std::thread::sleep(std::time::Duration::from_millis(700));
        let app_for_task = app.clone();
        let _ = app.run_on_main_thread(move || {
            if let Err(err) = create_pet(&app_for_task) {
                write_startup_log(&format!("宠物窗口没能打开，主窗口继续使用: {err}"));
            }
        });
    });
}

fn write_startup_log(text: &str) {
    let path = std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(|dir| dir.join("startup-error.txt")))
        .unwrap_or_else(|| std::path::PathBuf::from("startup-error.txt"));
    let _ = std::fs::write(path, text);
}

pub fn run() {
    let token = random_token();
    tauri::Builder::default()
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .manage(AppSecrets {
            token: token.clone(),
            api: Mutex::new(start_api(&token)),
        })
        .manage(DockState {
            saved: Mutex::new(None),
            active: Mutex::new(false),
        })
        .manage(PetState {
            visible: Mutex::new(true),
        })
        .invoke_handler(tauri::generate_handler![
            api_token,
            app_version,
            set_always_on_top,
            dock_apply,
            dock_restore,
            set_window_opacity,
            show_main,
            set_pet_visible,
            quit_app
        ])
        .setup(|app| {
            schedule_pet(app.handle().clone());
            Ok(())
        })
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
