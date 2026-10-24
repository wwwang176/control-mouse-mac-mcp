# control-mouse-mac-mcp

讓 AI（Claude Code、Claude Desktop 等 MCP client）透過截圖、滑鼠、鍵盤操作 **macOS** 的 MCP server。

這是 [control-mouse-mcp](https://github.com/wwwang176/control-mouse-mcp)（Windows 版）的 macOS 版本，工具名稱與參數盡量保持一致，同一套 prompt 兩邊都能用。底層直接呼叫 macOS API（Quartz `CGEvent`、Accessibility API、AppKit），不依賴 pyautogui。

## 功能

- **截圖**：主螢幕、指定區域、指定螢幕或所有螢幕；自動縮圖並回傳縮放比例，方便換算回螢幕座標
- **滑鼠**：點擊（左／右／中鍵、雙擊、搭配修飾鍵）、滾輪、拖曳；移動時有平滑的 ease-out 軌跡
- **鍵盤**：Unicode 輸入（中文、emoji 都能直接打）、組合鍵（`cmd+c`、`cmd+shift+s`…）
- **剪貼簿**：讀取／寫入文字
- **視窗管理**：列出視窗、切換焦點、最小化／最大化／還原／移動／調整大小
- **等待畫面變化**：監看某個區域，畫面有變化時回傳截圖
- **多螢幕**：列出所有螢幕及其座標範圍、解析度與縮放倍率
- **視覺提示**：
  - 畫面底部中央顯示目前執行的動作（例如 `Key: cmd+c`）
  - 游標周圍顯示光圈，移動時為金色、點擊時閃紅色
  - 提示視窗不會攔截滑鼠點擊；server 截圖時會暫時隱藏它，所以 AI 看到的截圖裡不會有它
  - 透過遠端桌面（AnyDesk、Chrome Remote Desktop、螢幕共享）也看得到提示視窗

## 需求

- macOS 14 以上（在 macOS 26 上開發與測試）
- [uv](https://docs.astral.sh/uv/)（用 `uvx` 安裝執行），或 Python 3.10 以上

## 安裝

### Claude Code

```bash
claude mcp add computer-mac-control -- \
  uvx --from git+https://github.com/wwwang176/control-mouse-mac-mcp control-mouse-mac-mcp
```

### Claude Desktop 或其他 MCP client

在設定檔的 `mcpServers` 加入：

```json
{
  "mcpServers": {
    "computer-mac-control": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/wwwang176/control-mouse-mac-mcp",
        "control-mouse-mac-mcp"
      ]
    }
  }
}
```

## 權限設定（重要）

需要兩個系統權限：

| 權限 | 用途 |
| --- | --- |
| **輔助使用**（Accessibility） | 送出滑鼠、鍵盤事件，操作其他 App 的視窗 |
| **螢幕與系統錄音**（Screen Recording） | 截圖、讀取視窗標題 |

macOS 會把權限記在**啟動 server 的那個 App** 上，而不是 Python：

- 在終端機裡用 Claude Code → 開給你的終端機（Terminal、iTerm2、Ghostty、Orca…）
- 用 Claude Desktop → 開給 Claude

步驟：

1. 打開「系統設定 → 隱私權與安全性 → 輔助使用」，打開上述 App。
2. 打開「系統設定 → 隱私權與安全性 → 螢幕與系統錄音」，打開同一個 App。
3. **完全結束該 App 再重新開啟**，權限才會生效。

server 第一次啟動時若缺權限，會自動跳出系統授權提示。工具執行時若缺權限，會回傳錯誤訊息，告訴你缺哪個權限、要開給哪個 App。`get_screen_info` 的 `permissions` 欄位也可以查目前狀態。

## 工具列表

| 工具 | 說明 |
| --- | --- |
| `screenshot` | 截圖。不帶參數為主螢幕；可指定 `left/top/right/bottom` 區域、`monitor=N` 或 `all_screens=true` |
| `get_screen_info` | 主螢幕大小與縮放倍率、虛擬桌面範圍、游標位置、前景 App 與視窗、螢幕列表、權限狀態 |
| `click` | 在 `(x, y)` 點擊。`button`：`left` / `right` / `middle`；`double=true` 雙擊；`keys` 指定按住的修飾鍵 |
| `scroll` | 在 `(x, y)` 滾動。`direction`：`up` / `down`；`clicks` 格數；`keys` 修飾鍵 |
| `drag` | 以左鍵從 `(x1, y1)` 拖曳到 `(x2, y2)` |
| `type_text` | 以 Unicode 輸入文字，支援任何語言；換行送 Return、Tab 送 Tab |
| `press_key` | 按下按鍵或組合鍵，例如 `enter`、`cmd+shift+s` |
| `clipboard_read` | 讀取剪貼簿文字 |
| `clipboard_write` | 寫入文字到剪貼簿 |
| `list_windows` | 列出所有可見視窗的 App、標題、位置與大小 |
| `focus_window` | 把符合的視窗帶到前景（正規表示式、不分大小寫，先比對視窗標題再比對 App 名稱） |
| `manage_window` | 對視窗做 `minimize` / `maximize` / `restore` / `move` / `resize` |
| `wait_for_change` | 等待某區域畫面變化，變化比例超過 `threshold` 或逾時就回傳截圖 |
| `list_monitors` | 列出所有螢幕的範圍（point）、解析度（pixel）、縮放倍率與是否為主螢幕 |

### 按鍵

- 修飾鍵：`cmd`（別名 `command`、`win`、`windows`）、`ctrl`（`control`）、`option`（`alt`、`opt`）、`shift`、`fn`
- 一般按鍵：`enter`（`return`）、`tab`、`escape`（`esc`）、`backspace`、`delete`（向前刪除）、`space`、方向鍵、`home`、`end`、`pageup`、`pagedown`、`capslock`、`f1`–`f12`、`a`–`z`、`0`–`9`、`-` `=` `[` `]` `;` `'` `,` `.` `/` `\` `` ` ``

`ctrl` 是真正的 Control 鍵，不會自動換成 `cmd`。macOS 上的快捷鍵大多用 `cmd`，例如複製是 `cmd+c`；`ctrl+c` 則是終端機的中斷。`insert`、`printscreen`、`numlock` 在 Mac 上沒有對應按鍵，會回傳錯誤。

### 與 Windows 版的差異

- 座標單位是 **point**（見下一節）。
- `list_windows` 回傳 `window_id`（取代 `hwnd`），並多了 `app`、`pid`。
- `focus_window`、`manage_window` 的 `title` 除了視窗標題也會比對 App 名稱。
- `maximize` 是把視窗調整成所在螢幕的可用區域（扣掉選單列與 Dock），不是全螢幕模式。

## 座標與縮放

所有工具使用 macOS 的 **point** 座標，原點在主螢幕左上角。Retina 螢幕上 1 point = 2 pixel，換算由 server 處理，你不需要自己乘 2。

截圖會縮小到預設 1280×720 以內以節省 token，回傳內容會附上區域左上角 `left/top` 與 `scale_x` / `scale_y`：

```
x = left + image_x * scale_x
y = top  + image_y * scale_y
```

全螢幕截圖時 `left/top` 為 0。

## `screenshot_after`

`click`、`scroll`、`drag`、`type_text`、`press_key` 都支援 `screenshot_after=true`，執行動作後會順便回傳動作點周圍 800×800 point 的截圖，省下一次額外的 `screenshot` 呼叫。

## 開發

```bash
git clone https://github.com/wwwang176/control-mouse-mac-mcp.git
cd control-mouse-mac-mcp
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'

# 單元測試
.venv/bin/python -m pytest

# 端對端測試：會實際移動滑鼠、打字（開一個專用的測試視窗），需要上述兩個權限
E2E=1 .venv/bin/python -m pytest tests/e2e -v
```

設計說明見 [docs/design.md](docs/design.md)。

## 注意事項

- 這個 server 能完全操控你的滑鼠與鍵盤，請只在你信任的 client 上使用。
- 只支援 macOS。Windows 請用 [control-mouse-mcp](https://github.com/wwwang176/control-mouse-mcp)。
- 系統開啟「自然捲動」時，server 會自動反轉滾輪方向，`up` 一律代表往上捲。
- Retina 與多螢幕的座標換算已依 point／pixel 分開處理，但目前只在單一非 Retina 螢幕上實測過。
