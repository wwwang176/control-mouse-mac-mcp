# control-mouse-mac-mcp 設計

[control-mouse-mcp](https://github.com/wwwang176/control-mouse-mcp)（Windows）的 macOS 版本：讓 MCP client 透過截圖、滑鼠、鍵盤、視窗工具操作 Mac。

## 目標

- 14 個工具與 Windows 版同名同參數，只加 Mac 必要的差異。
- 提示視窗（底部動作文字、游標光圈）不會被截進截圖。
- 公開發佈，支援 `uvx` 一行安裝；MCP 名稱為 `computer-mac-control`。
- 缺權限時回傳清楚的錯誤訊息：缺哪個權限、要開給哪個 App、開完要重啟。

## 可行性驗證結果（macOS 26.5）

| 項目 | 結果 |
|---|---|
| `NSWindow.sharingType = .none` 排除截圖 | `screencapture`、`CGWindowListCreateImage`、ScreenCaptureKit 都有效 |
| AppKit 主執行緒 + 背景執行緒 | 可行 |
| `CGEventPost` 滑鼠、Unicode 打字（中文、emoji）、組合鍵 | 可行（組合鍵需送出真正的修飾鍵按下／放開） |
| AX 讀寫其他 App 視窗的位置與大小 | 可行 |
| 權限 | 記在啟動 server 的 App（例如終端機）上，開完需重啟該 App |

## 技術選擇

- Python ≥ 3.10、PyObjC（Quartz、Cocoa、ApplicationServices）、Pillow、`mcp` 2.x（`MCPServer`）。
- 截圖使用系統內建的 `screencapture` 指令：Apple 持續維護、遵守 `sharingType`，約 100ms。不用已被標記停用的 `CGWindowListCreateImage`。

## 架構

單一行程：

- **主執行緒**：`NSApplication`（accessory，不出現在 Dock）事件迴圈，只負責提示視窗。
- **背景執行緒**：`MCPServer.run("stdio")`。同步工具由 anyio 丟到 worker thread 執行。
- 工具要更新提示視窗時，用 `call_on_main` 丟回主執行緒，不等待。
- 會操作滑鼠／鍵盤／視窗的工具共用一把鎖，避免同時執行時互相干擾。
- stdin 關閉 → `run()` 返回 → `NSApp.terminate_`，整個行程結束。

```
src/control_mouse_mac_mcp/
  __main__.py    進入點：建立 NSApplication、提示視窗，啟動 MCP 執行緒
  server.py      MCPServer 與工具定義（參數處理、組回傳結果）
  keymap.py      按鍵名稱 → keycode／修飾鍵旗標（純邏輯）
  geometry.py    座標換算、縮圖比例、區域裁切（純邏輯）
  input.py       CGEvent：移動、點擊、滾輪、拖曳、打字、組合鍵
  screen.py      截圖、螢幕列表、畫面變化比對
  windows.py     CGWindowList 列出視窗，AX 操作視窗
  clipboard.py   NSPasteboard
  overlay.py     提示視窗
  mainthread.py  call_on_main / run_on_main
  permissions.py 權限檢查與錯誤訊息
```

## 座標系

- 所有工具使用 **point** 座標，原點在主螢幕左上角（即 CG 全域座標）。這跟 `CGEvent` 一致，Retina 螢幕上不需要使用者自己處理 2 倍。
- 截圖輸出為 pixel，縮圖後回傳 `scale_x = 區域寬度(point) / 縮圖寬度`。
  換算公式：`x = left + image_x * scale_x`、`y = top + image_y * scale_y`（全螢幕時 left/top 為該螢幕原點，主螢幕為 0）。
- Cocoa（左下原點）只在 `overlay.py` 與取得螢幕可用區域時出現，由 `geometry.py` 換算。

## 工具對照

| 工具 | macOS 實作 | 與 Windows 版差異 |
|---|---|---|
| `screenshot` | `screencapture -R`（區域）／`-D`（單一螢幕）；`all_screens` 逐一截取後拼接 | 無 |
| `get_screen_info` | CGDisplay、CGEvent 游標位置、前景 App 與視窗標題 | 多 `scale`、`permissions` 欄位 |
| `click` | 滑鼠按下／放開事件，雙擊設定 click state = 2 | 無 |
| `scroll` | `CGEventCreateScrollWheelEvent`（以行為單位，每格 3 行）；系統開啟自然捲動時會套用到程式送出的事件，因此讀取設定並反轉方向 | 無 |
| `drag` | 按下 → 送出 `LeftMouseDragged` 平滑移動 → 放開 | 無 |
| `type_text` | `CGEventKeyboardSetUnicodeString`，每段 ≤ 20 個 UTF-16 單位；`\n` 送 Return、`\t` 送 Tab | 無 |
| `press_key` | keycode + 修飾鍵旗標；依序按下、反向放開 | 新增 `cmd`/`command`、`option`/`opt`、`fn`、標點符號；`win`/`windows` 為 `cmd` 別名；`ctrl` 是真正的 control；`insert`/`printscreen`/`numlock` 回傳不支援 |
| `clipboard_read` / `clipboard_write` | `NSPasteboard` | 無 |
| `list_windows` | `CGWindowListCopyWindowInfo`（layer 0、有標題） | `hwnd` 改為 `window_id`，多 `app`、`pid` |
| `focus_window` | AX：取消最小化、`AXRaise`、App 設為最前 | 正規表示式同時比對視窗標題與 App 名稱 |
| `manage_window` | AX：`AXMinimized`、`AXPosition`、`AXSize` | `maximize` 為調整成該螢幕的可用區域 |
| `wait_for_change` | 定時截取區域並比對 | 無 |
| `list_monitors` | `CGGetActiveDisplayList`，主螢幕排第一 | 多 `scale`、`pixel_width`、`pixel_height` |

## 提示視窗

- 兩個無邊框 `NSWindow`：`ignoresMouseEvents`、`sharingType = none`、狀態列層級、出現在所有桌面空間。
- 動作文字：主螢幕底部中央、距底部 120pt，深色半透明圓角背景、綠色粗體等寬字，1.5 秒後隱藏。
- 游標光圈：直徑 200pt 的圓環，移動時金色、點擊時紅色加粗；點擊 400ms 後恢復，閒置 800ms 後隱藏。

## 權限與錯誤處理

- 啟動時檢查輔助使用與螢幕錄製權限，缺少時觸發系統授權提示，並寫一行到 stderr（stdout 是 MCP 通道，不能輸出）。
- 工具執行前檢查需要的權限（輸入／視窗工具需要輔助使用，截圖工具需要螢幕錄製），缺少時以 `ToolError` 回傳：缺哪個權限、宿主 App 名稱（往上追父行程找到第一個 `.app`）、設定路徑、需重啟。
- 參數錯誤（未知按鍵、找不到視窗、找不到螢幕）同樣以 `ToolError` 回傳。

## 測試

- 單元測試（pytest）：`keymap`、`geometry`、畫面變化比例、視窗標題比對等純邏輯。
- 端對端：以 `mcp` client 透過 stdio 啟動 server，實際呼叫每個工具（需要權限，手動執行）。

## 未驗證

- Retina 與多螢幕：程式已依 point／pixel 分開處理，但開發機為單一 1920×1080 非 Retina 螢幕，尚未實測。
