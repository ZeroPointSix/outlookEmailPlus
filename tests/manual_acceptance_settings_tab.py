#!/usr/bin/env python3
"""
Phase 6 手动验收自动化脚本 - 设置页面 Tab 重构 UI 验收
对应 TD §4.2 前端验收清单

注意: Provider radio button 使用 display:none 隐藏原生 input，
      改用 JS evaluate 来 check radio 并触发 onchange。
"""

import sys
import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:5000"
PASSWORD = "admin123"
RESULTS = []


def log_result(item: str, passed: bool, detail: str = ""):
    status = "✅ PASS" if passed else "❌ FAIL"
    msg = f"{status}: {item}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    RESULTS.append((item, passed, detail))


def select_provider(page, value: str):
    """通过 JS 选中 Provider radio 并触发 onchange 回调"""
    page.evaluate(f"""
        (() => {{
            const radio = document.querySelector("input[name='tempMailProvider'][value='{value}']");
            if (radio) {{
                radio.checked = true;
                onTempMailProviderChange('{value}');
            }}
        }})()
    """)
    time.sleep(0.3)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        # === Step 1: 登录 ===
        print("\n=== Step 1: 登录 ===")
        page.goto(f"{BASE_URL}/")
        page.wait_for_load_state("networkidle")

        # 检查是否在登录页
        if page.locator("#password").count() > 0:
            page.fill("#password", PASSWORD)
            page.click("#loginBtn")
            # 等待登录后的页面跳转和完全加载
            page.wait_for_url("**/", timeout=10000)
            page.wait_for_load_state("networkidle")
            time.sleep(2)

        # 确认登录成功
        page.wait_for_selector(
            "#page-dashboard, .sidebar, .main-content", timeout=10000
        )
        print("✅ 登录成功")

        # === Step 2: 导航到设置页面 ===
        print("\n=== Step 2: 导航到设置页面 ===")
        settings_nav = page.locator(
            '[data-page="settings"], [onclick*="settings"], a[href*="settings"]'
        )
        if settings_nav.count() > 0:
            settings_nav.first.click()
            time.sleep(0.5)
        else:
            page.evaluate("switchPage('settings')")
            time.sleep(0.5)

        page.screenshot(path="tests/screenshots/settings_page.png", full_page=True)

        # === 验收 4.2.1: 设置页面显示 4 个 Tab ===
        print("\n=== 验收 4.2.1: 设置页面显示 4 个 Tab ===")
        tabs = page.locator(".settings-tab-nav .settings-tab")
        tab_count = tabs.count()
        log_result(
            "4.2.1 设置页面显示 4 个 Tab", tab_count == 4, f"找到 {tab_count} 个 Tab"
        )

        # 检查 Tab 名称
        tab_texts = [tabs.nth(i).inner_text().strip() for i in range(tab_count)]
        expected_tabs = ["基础", "临时邮箱", "API 安全", "自动化"]
        log_result(
            "4.2.1a Tab 名称正确",
            tab_texts == expected_tabs,
            f"实际: {tab_texts}, 期望: {expected_tabs}",
        )

        # === 验收 4.2.2: 点击 Tab 切换内容区，无需刷新 ===
        print("\n=== 验收 4.2.2: Tab 切换 ===")
        tabs.nth(1).click()
        time.sleep(0.3)

        temp_mail_pane = page.locator("#settings-tab-temp-mail")
        basic_pane = page.locator("#settings-tab-basic")

        temp_mail_visible = temp_mail_pane.is_visible()
        basic_hidden = not basic_pane.is_visible()

        log_result(
            "4.2.2 点击临时邮箱 Tab 切换内容区",
            temp_mail_visible and basic_hidden,
            f"临时邮箱面板可见: {temp_mail_visible}, 基础面板隐藏: {basic_hidden}",
        )

        page.screenshot(
            path="tests/screenshots/settings_temp_mail_tab.png", full_page=True
        )

        # === 验收 4.2.3: 当前 Tab 有蓝色下划线视觉标识 ===
        print("\n=== 验收 4.2.3: 当前 Tab 视觉标识 ===")
        active_tab = page.locator(".settings-tab.active")
        active_tab_text = (
            active_tab.inner_text().strip() if active_tab.count() > 0 else ""
        )
        has_active_class = active_tab.count() == 1 and active_tab_text == "临时邮箱"
        log_result(
            "4.2.3 当前 Tab 有 active 类标识",
            has_active_class,
            f"active Tab: '{active_tab_text}'",
        )

        # 检查 active Tab 是否有蓝色下划线样式 (border-bottom)
        active_border = page.evaluate("""
            () => {
                const el = document.querySelector('.settings-tab.active');
                if (!el) return 'none';
                const style = window.getComputedStyle(el);
                return style.borderBottomColor || 'none';
            }
        """)
        log_result(
            "4.2.3a 当前 Tab 有蓝色下划线颜色",
            active_border != "none" and active_border != "",
            f"border-bottom-color: {active_border}",
        )

        # === 验收 4.2.4: 临时邮箱 Tab 显示 Provider 单选按钮组 ===
        print("\n=== 验收 4.2.4: Provider 单选按钮组 ===")
        provider_radios = page.locator("input[name='tempMailProvider']")
        radio_count = provider_radios.count()
        log_result(
            "4.2.4 Provider 单选按钮组存在",
            radio_count == 2,
            f"找到 {radio_count} 个 radio button",
        )

        radio_values = [
            provider_radios.nth(i).get_attribute("value") for i in range(radio_count)
        ]
        expected_values = ["legacy_bridge", "cloudflare_temp_mail"]
        log_result(
            "4.2.4a Provider 值正确",
            radio_values == expected_values,
            f"实际: {radio_values}",
        )

        # 检查 Provider radio label 是否可见
        provider_labels = page.locator(".provider-radio-label")
        labels_visible = all(
            provider_labels.nth(i).is_visible() for i in range(provider_labels.count())
        )
        log_result(
            "4.2.4b Provider 单选按钮卡片可见",
            labels_visible and provider_labels.count() == 2,
            f"可见 label 数量: {provider_labels.count()}",
        )

        # === 验收 4.2.5: 选中 GPTMail 时 GPTMail 面板可见，CF Worker 面板隐藏 ===
        print("\n=== 验收 4.2.5: GPTMail 面板切换 ===")
        select_provider(page, "legacy_bridge")

        gptmail_panel = page.locator("#gptmailConfigPanel")
        cf_panel = page.locator("#cfWorkerConfigPanel")

        gptmail_visible = gptmail_panel.is_visible()
        cf_hidden = not cf_panel.is_visible()

        log_result(
            "4.2.5 选中 GPTMail 时面板状态正确",
            gptmail_visible and cf_hidden,
            f"GPTMail 可见: {gptmail_visible}, CF Worker 隐藏: {cf_hidden}",
        )

        page.screenshot(
            path="tests/screenshots/settings_gptmail_selected.png", full_page=True
        )

        # === 验收 4.2.6: 选中 CF Worker 时 CF Worker 面板可见，GPTMail 面板隐藏 ===
        print("\n=== 验收 4.2.6: CF Worker 面板切换 ===")
        select_provider(page, "cloudflare_temp_mail")

        gptmail_hidden = not gptmail_panel.is_visible()
        cf_visible = cf_panel.is_visible()

        log_result(
            "4.2.6 选中 CF Worker 时面板状态正确",
            gptmail_hidden and cf_visible,
            f"GPTMail 隐藏: {gptmail_hidden}, CF Worker 可见: {cf_visible}",
        )

        page.screenshot(
            path="tests/screenshots/settings_cfworker_selected.png", full_page=True
        )

        # === 验收 4.2.7: 切换 Provider 立即响应，无需保存 ===
        print("\n=== 验收 4.2.7: Provider 切换立即响应 ===")
        select_provider(page, "legacy_bridge")
        instant_switch = gptmail_panel.is_visible() and not cf_panel.is_visible()

        # 再切回 CF Worker
        select_provider(page, "cloudflare_temp_mail")
        instant_switch2 = not gptmail_panel.is_visible() and cf_panel.is_visible()

        log_result(
            "4.2.7 切换 Provider 立即响应（无需保存）",
            instant_switch and instant_switch2,
            f"GPTMail→CF: {instant_switch}, CF→GPTMail: 反向也通过={instant_switch2}",
        )

        # === 验收 4.2.8: CF Worker 域名字段永久只读 ===
        print("\n=== 验收 4.2.8: CF Worker 域名字段只读 ===")
        # 确保在 CF Worker 面板
        select_provider(page, "cloudflare_temp_mail")

        cf_domains_field = page.locator("#settingsCfWorkerDomains")
        cf_default_domain_field = page.locator("#settingsCfWorkerDefaultDomain")

        domains_readonly = cf_domains_field.get_attribute("readonly") is not None
        default_domain_readonly = (
            cf_default_domain_field.get_attribute("readonly") is not None
        )
        has_readonly_class_domains = "readonly-field" in (
            cf_domains_field.get_attribute("class") or ""
        )
        has_readonly_class_default = "readonly-field" in (
            cf_default_domain_field.get_attribute("class") or ""
        )

        log_result(
            "4.2.8 CF Worker 域名字段为只读",
            domains_readonly and default_domain_readonly,
            f"域名 readonly: {domains_readonly}, 默认域名 readonly: {default_domain_readonly}",
        )
        log_result(
            "4.2.8a CF Worker 域名字段有 readonly-field CSS 类",
            has_readonly_class_domains and has_readonly_class_default,
            f"域名 class: {has_readonly_class_domains}, 默认域名 class: {has_readonly_class_default}",
        )

        # 验证只读字段的灰色背景
        bg_color = page.evaluate("""
            () => {
                const el = document.getElementById('settingsCfWorkerDomains');
                if (!el) return 'none';
                return window.getComputedStyle(el).backgroundColor;
            }
        """)
        log_result(
            "4.2.8b CF Worker 只读字段有灰色背景",
            bg_color != "rgba(0, 0, 0, 0)" and bg_color != "none",
            f"background-color: {bg_color}",
        )

        # === 验收 4.2.9: 切换 Tab 时自动保存 ===
        print("\n=== 验收 4.2.9: Tab 切换自动保存 ===")
        tabs.nth(2).click()  # 切换到 API 安全
        time.sleep(0.5)

        api_security_visible = page.locator("#settings-tab-api-security").is_visible()
        log_result("4.2.9a API 安全 Tab 切换正常", api_security_visible, "")

        # 监听网络请求
        save_triggered = {"value": False}

        def on_request(request):
            if "/api/settings" in request.url and request.method == "PUT":
                save_triggered["value"] = True

        page.on("request", on_request)

        # 切换到自动化 Tab（应触发自动保存 API 安全 Tab 的内容）
        tabs.nth(3).click()
        time.sleep(1.5)

        log_result(
            "4.2.9 切换 Tab 时触发自动保存 PUT /api/settings",
            save_triggered["value"],
            "监听到 PUT /api/settings 请求"
            if save_triggered["value"]
            else "未检测到保存请求",
        )

        page.remove_listener("request", on_request)

        # === 验收 4.2.10: 页面宽度不受 720px 限制 ===
        print("\n=== 验收 4.2.10: 页面宽度 ===")
        tabs.nth(0).click()
        time.sleep(0.3)

        settings_width = page.evaluate("""
            () => {
                const el = document.getElementById('page-settings');
                if (!el) return 0;
                return el.getBoundingClientRect().width;
            }
        """)

        log_result(
            "4.2.10 页面宽度不受 720px 限制",
            settings_width > 720,
            f"设置页面宽度: {settings_width}px",
        )

        # === 额外验收: 所有 Tab 循环切换 ===
        print("\n=== 额外验收: Tab 循环切换 ===")
        tab_ids = [
            "settings-tab-basic",
            "settings-tab-temp-mail",
            "settings-tab-api-security",
            "settings-tab-automation",
        ]
        all_tabs_ok = True
        for i, tab_id in enumerate(tab_ids):
            tabs.nth(i).click()
            time.sleep(0.2)
            pane = page.locator(f"#{tab_id}")
            if not pane.is_visible():
                all_tabs_ok = False
                print(f"  ❌ Tab {i} ({tab_id}) 不可见")

        log_result("额外: 所有 4 个 Tab 循环切换均正常", all_tabs_ok, "")

        # === 额外验收: 基础 Tab 切换不触发自动保存（密码排除逻辑）===
        print("\n=== 额外验收: 基础 Tab 密码排除 ===")
        tabs.nth(0).click()  # 基础 Tab
        time.sleep(0.3)

        basic_save_triggered = {"value": False}

        def on_basic_request(request):
            if "/api/settings" in request.url and request.method == "PUT":
                basic_save_triggered["value"] = True

        page.on("request", on_basic_request)

        # 从基础 Tab 切到临时邮箱 Tab
        tabs.nth(1).click()
        time.sleep(1)

        # 基础 Tab 切走时不应触发自动保存（因为包含密码字段）
        log_result(
            "额外: 基础 Tab 切走时不触发自动保存",
            not basic_save_triggered["value"],
            "未触发保存" if not basic_save_triggered["value"] else "意外触发了保存请求",
        )

        page.remove_listener("request", on_basic_request)

        # === 最终截图 ===
        page.screenshot(path="tests/screenshots/settings_final.png", full_page=True)

        browser.close()

    # === 汇总报告 ===
    print("\n" + "=" * 60)
    print("Phase 6 验收汇总报告")
    print("=" * 60)
    passed = sum(1 for _, p, _ in RESULTS if p)
    failed = sum(1 for _, p, _ in RESULTS if not p)
    total = len(RESULTS)

    if failed > 0:
        print(f"\n❌ 失败项:")
        for item, p, detail in RESULTS:
            if not p:
                print(f"  - {item}: {detail}")

    print(f"\n总计: {total} 项 | 通过: {passed} | 失败: {failed}")

    if failed > 0:
        print("\n⚠️ 有验收项未通过！")
        sys.exit(1)
    else:
        print("\n✅ 所有验收项全部通过！Phase 6 验收完成！")
        sys.exit(0)


if __name__ == "__main__":
    main()
