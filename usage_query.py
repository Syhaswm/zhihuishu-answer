"""各模型厂商用量 / 余额查询（界面统一，按厂商分别对接官方接口）。"""

from __future__ import annotations

import requests

from answer import find_provider, provider_endpoint, session

CONSOLE_URLS = {
    "deepseek": "https://platform.deepseek.com/",
    "qwen": "https://bailian.console.aliyun.com/",
    "zhipu": "https://open.bigmodel.cn/usercenter/balance",
    "kimi": "https://platform.moonshot.cn/console",
    "doubao": "https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement",
    "openai": "https://platform.openai.com/settings/organization/billing",
    "gemini": "https://aistudio.google.com/",
    "ollama": "https://ollama.com/",
    "lmstudio": "https://lmstudio.ai/",
    "custom": "",
}


def _row(label, value, hint=""):
    text = str(value or "").strip()
    if not text and text != "0":
        return None
    item = {"label": label, "value": text}
    if hint:
        item["hint"] = hint
    return item


def _rows(*items):
    out = []
    for item in items:
        if item:
            out.append(item)
    return out


def _http_error(name, response, payload):
    message = ""
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            message = str(err.get("message") or "")
        message = message or str(payload.get("msg") or payload.get("message") or "")
    return RuntimeError(f"{name} {response.status_code}：" + (message or response.text[:200]))


def _get_json(url, api_key, auth_modes=("bearer",), timeout=20):
    last_error = None
    for mode in auth_modes:
        headers = {"Accept": "application/json"}
        key = str(api_key or "").strip()
        if mode == "bearer" and key:
            headers["Authorization"] = f"Bearer {key}"
        elif mode == "raw" and key:
            headers["Authorization"] = key
        elif mode == "none":
            pass
        else:
            continue
        try:
            response = session().get(url, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            last_error = exc
            continue
        try:
            payload = response.json()
        except ValueError:
            last_error = RuntimeError(f"HTTP {response.status_code} 返回不是 JSON")
            continue
        if response.ok:
            return payload
        last_error = _http_error("", response, payload)
    if last_error:
        raise last_error
    raise RuntimeError("请求失败")


def _result(found, supported, rows, note="", console_key=None):
    return {
        "ok": True,
        "supported": bool(supported),
        "name": found["name"],
        "rows": rows or [],
        "note": note or "",
        "consoleUrl": CONSOLE_URLS.get(console_key or found["id"], ""),
    }


def _usage_deepseek(found, _base_url, api_key):
    data = _get_json("https://api.deepseek.com/user/balance", api_key)
    rows = []
    for info in data.get("balance_infos") or []:
        currency = info.get("currency") or ""
        rows.extend(
            _rows(
                _row(f"总余额 ({currency})", info.get("total_balance")),
                _row("充值余额", info.get("topped_up_balance")),
                _row("赠送余额", info.get("granted_balance")),
            )
        )
    note = ""
    if data.get("is_available") is False:
        note = "当前余额可能不足以调用 API，请到控制台充值。"
    if not rows:
        rows = [_row("状态", "已查询", "接口未返回余额明细")]
    return _result(found, True, rows, note)


def _usage_qwen(found, _base_url, api_key):
    data = _get_json(
        "https://dashscope.aliyuncs.com/api/v1/recharge/recharge-balance/query",
        api_key,
    )
    rows = []
    if isinstance(data, dict):
        balance = data.get("balance")
        currency = data.get("currency") or "CNY"
        if balance is None and isinstance(data.get("data"), dict):
            balance = data["data"].get("balance") or data["data"].get("availableBalance")
            currency = data["data"].get("currency") or currency
        if balance is not None:
            rows.append(_row("可用余额", f"{balance} {currency}"))
    if not rows:
        rows = [_row("查询结果", str(data)[:120])]
    return _result(found, True, rows)


def _usage_zhipu(found, _base_url, api_key):
    rows = []
    note_parts = []
    try:
        report = _get_json(
            "https://open.bigmodel.cn/api/biz/account/query-customer-account-report",
            api_key,
            auth_modes=("bearer", "raw"),
        )
        data = report.get("data") if isinstance(report, dict) else None
        if isinstance(data, dict):
            rows.extend(
                _rows(
                    _row("可用余额", _money(data.get("availableBalance"), "CNY")),
                    _row("账户余额", _money(data.get("balance"), "CNY")),
                    _row("累计充值", _money(data.get("rechargeAmount"), "CNY")),
                    _row("赠送金额", _money(data.get("giveAmount"), "CNY")),
                    _row("累计消费", _money(data.get("totalSpendAmount"), "CNY")),
                    _row("冻结余额", _money(data.get("frozenBalance"), "CNY")),
                )
            )
    except RuntimeError as exc:
        note_parts.append(f"账户余额：{exc}")

    try:
        quota = _get_json(
            "https://open.bigmodel.cn/api/monitor/usage/quota/limit",
            api_key,
            auth_modes=("raw", "bearer"),
        )
        payload = quota.get("data") if isinstance(quota, dict) else None
        if isinstance(payload, dict):
            level = str(payload.get("level") or "").strip()
            if level:
                rows.append(_row("套餐等级", level.upper()))
            for item in payload.get("limits") or []:
                if not isinstance(item, dict):
                    continue
                kind = item.get("type") or "额度"
                if kind == "TOKENS_LIMIT":
                    used = item.get("percentage")
                    if used is not None:
                        rows.append(_row("Token 额度已用", f"{used}%", "Coding Plan 类套餐"))
                elif kind == "TIME_LIMIT":
                    rows.append(
                        _row(
                            "MCP 本月",
                            f"剩余 {item.get('remaining', '—')} / {item.get('usage', '—')} 次",
                        )
                    )
    except RuntimeError as exc:
        note_parts.append(f"套餐额度：{exc}")

    if rows:
        return _result(found, True, rows, "；".join(note_parts))
    if note_parts:
        raise RuntimeError("；".join(note_parts))
    raise RuntimeError("智谱未返回可用的余额或额度信息（部分 Key 仅支持对话，不支持查询）。")


def _money(value, unit):
    if value is None:
        return ""
    return f"¥{value}" if unit == "CNY" else f"{value} {unit}"


def _kimi_balance_url(base_url):
    root = str(base_url or "").lower()
    if "moonshot.ai" in root:
        return "https://api.moonshot.ai/v1/users/me/balance"
    return "https://api.moonshot.cn/v1/users/me/balance"


def _usage_kimi(found, base_url, api_key):
    urls = [_kimi_balance_url(base_url)]
    if urls[0].endswith(".cn/v1/users/me/balance"):
        urls.append("https://api.moonshot.ai/v1/users/me/balance")
    else:
        urls.append("https://api.moonshot.cn/v1/users/me/balance")
    last_error = None
    for url in urls:
        try:
            payload = _get_json(url, api_key)
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                continue
            rows = _rows(
                _row("可用余额", f"${data.get('available_balance')} USD"),
                _row("代金券", f"${data.get('voucher_balance')} USD"),
                _row("现金余额", f"${data.get('cash_balance')} USD"),
            )
            if rows:
                note = ""
                if float(data.get("available_balance") or 0) <= 0:
                    note = "可用余额 ≤ 0 时无法调用推理 API。"
                return _result(found, True, rows, note)
        except RuntimeError as exc:
            last_error = exc
    raise last_error or RuntimeError("Kimi 余额查询失败，请确认 Key 与平台（.cn / .ai）一致。")


def _usage_openai(found, _base_url, api_key):
    try:
        data = _get_json("https://api.openai.com/v1/dashboard/billing/credit_grants", api_key)
        total = data.get("total_available") or data.get("total_granted")
        used = data.get("total_used")
        rows = _rows(
            _row("可用赠金", f"${total}" if total is not None else ""),
            _row("已使用", f"${used}" if used is not None else ""),
        )
        if rows:
            return _result(found, True, rows, "部分账号此接口已停用，以控制台为准。")
    except RuntimeError:
        pass
    return _result(
        found,
        False,
        [],
        "OpenAI 未提供稳定的 API Key 余额接口，请到控制台查看账单与剩余额度。",
    )


def _usage_gemini(found, _base_url, api_key):
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        response = session().get(url, timeout=20)
        payload = response.json()
        if response.ok and isinstance(payload, dict):
            models = payload.get("models") or []
            return _result(
                found,
                False,
                [_row("可调用模型数", str(len(models)))],
                "Gemini 配额与账单请在 Google AI Studio 查看，API 不返回余额。",
            )
    except (requests.RequestException, ValueError):
        pass
    return _result(
        found,
        False,
        [],
        "Gemini 请在 Google AI Studio 查看免费额度与用量。",
    )


def _usage_doubao(found, _base_url, _api_key):
    return _result(
        found,
        False,
        [],
        "豆包（火山方舟）余额与免费额度需在火山引擎控制台查看，API Key 暂无统一余额接口。",
    )


def _usage_ollama(found, base_url, _api_key):
    host = "http://127.0.0.1:11434"
    if "11434" in str(base_url or ""):
        parsed = str(base_url).split("/v1")[0].rstrip("/")
        if parsed.startswith("http"):
            host = parsed
    rows = []
    try:
        tags = _get_json(f"{host}/api/tags", "", auth_modes=("none",))
        models = tags.get("models") if isinstance(tags, dict) else []
        rows.append(_row("本机模型数", str(len(models) if isinstance(models, list) else 0)))
    except RuntimeError:
        raise RuntimeError("连不上本机 Ollama，请先启动服务。")
    try:
        ps = _get_json(f"{host}/api/ps", "", auth_modes=("none",))
        running = ps.get("models") if isinstance(ps, dict) else []
        rows.append(_row("正在运行", str(len(running) if isinstance(running, list) else 0)))
    except RuntimeError:
        pass
    return _result(found, True, rows, "本地模型无云端账单，仅显示本机状态。")


def _usage_lmstudio(found, base_url, _api_key):
    endpoint = provider_endpoint(found, base_url)
    root = str(endpoint or found["url"]).strip().rstrip("/")
    if root.endswith("/chat/completions"):
        root = root[: -len("/chat/completions")]
    urls = [root + "/models", root.rstrip("/") + "/v1/models"]
    last_error = None
    for url in urls:
        try:
            payload = _get_json(url, "", auth_modes=("none",))
            names = []
            if isinstance(payload, dict):
                for item in payload.get("data") or []:
                    if isinstance(item, dict):
                        names.append(item.get("id") or item.get("name"))
            rows = [_row("已加载模型数", str(len([n for n in names if n])))]
            return _result(found, True, rows, "本地 LM Studio 无云端账单，仅显示本机模型数。")
        except RuntimeError as exc:
            last_error = exc
    raise last_error or RuntimeError("连不上 LM Studio 本地服务，请先打开本地服务器。")


def _usage_custom(found, base_url, api_key):
    endpoint = provider_endpoint(found, base_url)
    if not endpoint.startswith(("http://", "https://")):
        return _result(found, False, [], "请填写自定义接口地址。第三方服务是否支持用量查询取决于对方是否提供接口。")
    try:
        root = endpoint.rstrip("/")
        if root.endswith("/chat/completions"):
            root = root[: -len("/chat/completions")]
        _get_json(root + "/models", api_key, auth_modes=("bearer", "none"))
        return _result(
            found,
            False,
            [_row("接口状态", "可访问")],
            "自定义接口未配置用量查询，请到服务商控制台查看。",
        )
    except RuntimeError:
        return _result(found, False, [], "自定义接口未提供标准用量 API，请到服务商控制台查看。")


_HANDLERS = {
    "deepseek": _usage_deepseek,
    "qwen": _usage_qwen,
    "zhipu": _usage_zhipu,
    "kimi": _usage_kimi,
    "doubao": _usage_doubao,
    "openai": _usage_openai,
    "gemini": _usage_gemini,
    "ollama": _usage_ollama,
    "lmstudio": _usage_lmstudio,
    "custom": _usage_custom,
}


def query_usage(provider_id, base_url, api_key):
    found = find_provider(provider_id)
    if found["needsKey"] and not str(api_key or "").strip():
        raise RuntimeError(f"请先填写{found['name']}的 API Key，再查询用量。")
    handler = _HANDLERS.get(found["id"], _usage_custom)
    return handler(found, base_url, api_key)
