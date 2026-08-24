// ==UserScript==
// @name         NovelTracker 浏览器接力同步助手 (Relay Assistant)
// @namespace    https://github.com/Shengxuan2513/novel-tracker
// @version      2.0.0
// @description  一键将当前浏览器打开的小说章节（包括受 Cloudflare 5秒盾、VIP 保护的页面）无缝同步至本地 NovelTracker
// @author       NovelTracker
// @match        *://*/*
// @grant        GM_xmlhttpRequest
// @grant        GM_notification
// @grant        GM_setValue
// @grant        GM_getValue
// @connect      127.0.0.1
// ==/UserScript==

(function () {
    'use strict';

    const RELAY_API = 'http://127.0.0.1:8765/api/relay';

    // Heuristic detection: is this a novel chapter page?
    function isNovelPage() {
        const bodyText = document.body ? document.body.innerText : '';
        const title = document.title || '';
        const hasChapterKw = /第\s*[0-9零一二两三四五六七八九十百千万]+\s*[章节回集卷篇节]/.test(title) ||
                             /第\s*[0-9零一二两三四五六七八九十百千万]+\s*[章节回集卷篇节]/.test(bodyText.substring(0, 1000));
        const hasContent = document.querySelector('#content, #chaptercontent, .read-content, #txtContent, article, .chapter-box, .novel-content');
        return (hasChapterKw || hasContent) && bodyText.length > 300;
    }

    if (!isNovelPage()) return;

    // Parse book and chapter title
    function extractMeta() {
        let title = document.title;
        let bookTitle = '未知小说';
        let chapterTitle = '正文章节';

        // Extract book name from 《...》
        const bookMatch = title.match(/《(.*?)》/);
        if (bookMatch) {
            bookTitle = bookMatch[1];
        } else {
            // Split by _ or -
            const parts = title.split(/[_|\-—]/);
            if (parts.length > 1) {
                bookTitle = parts[parts.length - 1].replace(/最新章节|全文阅读|小说/g, '').trim();
            }
        }

        const h1 = document.querySelector('h1');
        if (h1 && h1.innerText.trim()) {
            chapterTitle = h1.innerText.trim();
        } else {
            const chapMatch = title.match(/(第\s*[0-9零一二两三四五六七八九十百千万]+\s*[章节回集卷篇节][^\s_\-|]+)/);
            if (chapMatch) {
                chapterTitle = chapMatch[1];
            } else {
                chapterTitle = title.split(/[_|\-—]/)[0].trim();
            }
        }

        return { bookTitle, chapterTitle };
    }

    // Floating UI
    const container = document.createElement('div');
    container.id = 'novel-tracker-relay-widget';
    container.innerHTML = `
        <div style="
            position: fixed;
            bottom: 30px;
            right: 25px;
            z-index: 999999;
            background: linear-gradient(135deg, #1e293b, #0f172a);
            color: #f8fafc;
            padding: 12px 16px;
            border-radius: 12px;
            box-shadow: 0 10px 25px -5px rgba(0,0,0,0.4), 0 8px 10px -6px rgba(0,0,0,0.3);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: 13px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            border: 1px solid rgba(255,255,255,0.15);
            backdrop-filter: blur(8px);
        ">
            <div style="font-weight: bold; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 6px;">
                <span>📚 NovelTracker 接力</span>
                <span id="nt-status" style="font-size: 11px; color: #94a3b8;">就绪</span>
            </div>
            <button id="nt-sync-btn" style="
                background: #3b82f6;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 6px;
                cursor: pointer;
                font-weight: 500;
                transition: all 0.2s;
            ">⚡ 一键同步本章</button>
            <label style="display: flex; align-items: center; gap: 6px; font-size: 11px; color: #cbd5e1; cursor: pointer;">
                <input type="checkbox" id="nt-auto-sync"> 翻页自动连读同步
            </label>
        </div>
    `;
    document.body.appendChild(container);

    const syncBtn = document.getElementById('nt-sync-btn');
    const statusText = document.getElementById('nt-status');
    const autoSyncCheckbox = document.getElementById('nt-auto-sync');

    autoSyncCheckbox.checked = GM_getValue('nt_auto_sync', false);
    autoSyncCheckbox.addEventListener('change', () => {
        GM_setValue('nt_auto_sync', autoSyncCheckbox.checked);
    });

    function doSync() {
        statusText.innerText = '同步中...';
        statusText.style.color = '#fbbf24';
        syncBtn.disabled = true;

        const meta = extractMeta();
        const payload = {
            book_title: meta.bookTitle,
            chapter_title: meta.chapterTitle,
            html: document.documentElement.outerHTML,
            url: window.location.href
        };

        GM_xmlhttpRequest({
            method: 'POST',
            url: RELAY_API,
            headers: { 'Content-Type': 'application/json' },
            data: JSON.stringify(payload),
            timeout: 5000,
            onload: function (resp) {
                syncBtn.disabled = false;
                if (resp.status === 200) {
                    const res = JSON.parse(resp.responseText);
                    statusText.innerText = `已同步 (${res.character_count}字)`;
                    statusText.style.color = '#4ade80';
                    syncBtn.innerText = '✅ 同步成功';
                    setTimeout(() => { syncBtn.innerText = '⚡ 再次同步本章'; }, 3000);
                } else {
                    statusText.innerText = '同步失败';
                    statusText.style.color = '#f87171';
                }
            },
            onerror: function () {
                syncBtn.disabled = false;
                statusText.innerText = '服务未启动';
                statusText.style.color = '#f87171';
                alert('⚠️ 本地 NovelTracker 接力服务未运行！\n请先在终端中执行：\npython cli.py relay');
            }
        });
    }

    syncBtn.addEventListener('click', doSync);

    // Auto-sync on page load if enabled
    if (autoSyncCheckbox.checked) {
        setTimeout(doSync, 1000);
    }
})();
