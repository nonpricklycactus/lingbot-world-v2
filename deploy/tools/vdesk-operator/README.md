# vdesk-operator —— 在虚拟显示器上以"拟人节奏"操作 Windows 并录像

给录屏用的一套小工具：把命令**逐字敲进**一块虚拟显示器上的终端，鼠标按拟人轨迹移动、点击，
同时只录制那块虚拟屏的区域。主显示器完全不受影响，用户可以在主屏上做别的事。

## 为什么是这个方案

| 试过的路子 | 结果 |
|---|---|
| 直接录主屏 | 会把用户的私人窗口一起录进去；操作时还会抢焦点 |
| Windows 隐藏桌面 (`CreateDesktop`) | **能启动进程，但抓不到画面** —— 非活动桌面不被合成，GDI 抓出来整张全黑 |
| 裸 `powershell.exe` 窗口 | 控制台窗口属于 `conhost.exe`，从进程外枚举不到、也搬不动；且不加 `-NoExit` 会一闪就没 |
| **虚拟显示器 + Windows Terminal**（采用） | `wt --pos 2560,0` 直接把窗口开在虚拟屏上，主屏不闪；DWM 正常合成，可录制 |

## 文件

| 文件 | 作用 |
|---|---|
| `type_into_vdesk.py` | 主入口：读命令清单 → 在虚拟屏开/复用 Windows Terminal → 逐字敲入 |
| `hidlink/` | vendored 自同一作者的桌面自动化实现：SendInput 注入、拟人轨迹、串口协议等；此处只用 `backends` / `trajectory` |
| `vdesk-shell.ps1` | 终端启动脚本（设窗口标题；窗口位置由 Python 侧用 `SetWindowPos` 摆放） |
| `DisplayInfo.cs` | DPI 感知的显示器枚举工具源码，`csc /target:exe` 编译后可直接看物理像素坐标 |
| `steps/*.txt` | 分步命令清单（LingBot 部署手册 §2.1–§4.1） |

## 前置：一块虚拟显示器

本工具**不自带**虚拟显示器。本机装的是 Virtual Display Driver (VDD by MTT)：
`github.com/VirtualDrivers/Virtual-Display-Driver`，驱动签名 SignPath Foundation，`Get-AuthenticodeSignature` 为 `Valid`。

```powershell
# 1) 加驱动包 (管理员)
pnputil /add-driver "<dir>\MttVDD.inf" /install
# 2) 创建 root 设备节点 —— pnputil 只入库, 不建节点, 这步不能省 (管理员)
devcon install "<dir>\MttVDD.inf" Root\MttVDD
# 3) 把桌面扩展到虚拟屏
DisplaySwitch.exe /extend
# 验证: 应看到两行, 第二行在 x=2560
DisplayInfo.exe
```

配置在 `C:\VirtualDisplayDriver\vdd_settings.xml`（台数/分辨率/刷新率）。

回滚：

```powershell
DisplaySwitch.exe /internal
devcon remove "Root\MttVDD"
pnputil /delete-driver oem88.inf /uninstall /force
```

> 官方 README 提醒：升级显卡驱动前先卸载 VDD；万一黑屏或显示优先级错乱，进安全模式卸载。

## 用法

```powershell
# 在虚拟屏新开终端并敲一份清单
python type_into_vdesk.py steps\steps-00-environment.txt

# 复用已开着的那个终端（不重开窗口）
python type_into_vdesk.py steps\steps-01-hardware.txt --reuse --zoom=0
```

只录虚拟屏那一块（`-draw_mouse 1` 把鼠标光标画进画面）：

```powershell
ffmpeg -f gdigrab -draw_mouse 1 -offset_x 2560 -offset_y 0 -video_size 1920x1080 `
       -framerate 15 -i desktop -t 90 -c:v libx264 -preset veryfast -crf 24 `
       -pix_fmt yuv420p -y out.mp4
```

## 命令清单格式

每行一条；`#` 开头是注释。

| 指令 | 作用 |
|---|---|
| `WAIT 2.5` | 纯等待（长命令要留够，比如 `git clone`） |
| `WHEEL 5` | 鼠标滚轮往上滚 5 格（把上面的输出滑回视野） |
| `CLS` | 清屏（等价输入 `cls` 回车） |
| `CLEAR` | 不输入任何可见字符，只按 Ctrl+L |
| 其他 | 当作命令逐字敲进去并回车 |

清单里**不要**写解释性提示 —— 讲解留给配音，画面只跑真命令。

## 踩过的坑（都会重犯，写下来）

1. **`-NoExit` 不能省**。`powershell -File x.ps1` 跑完就退出，窗口一闪而过，看起来像"闪到主屏上"。
2. **控制台窗口属于 `conhost.exe`**。按 PowerShell 进程 PID 找窗口会找错；要按类名 `ConsoleWindowClass` 找。
3. **`subprocess.Popen` 必须带 `CREATE_NEW_CONSOLE`**，否则子进程共用父进程控制台，虚拟屏上根本没有新窗口。
4. **Windows Terminal 的窗口类名是 `CASCADIA_HOSTING_WINDOW_CLASS`**，用 `--pos` 可以直接开在指定坐标，避免在主屏闪一下。
5. **先声明 DPI 感知再算坐标**。非 DPI 感知进程把 2560x1600 看成 1707x1067，多屏绝对坐标会落错位置。
6. **敲键盘前必须校验前台窗口**。否则按键会打进别的窗口（比如聊天窗口），这是不可接受的副作用。
7. **窗口要比屏幕小一圈**。铺满屏幕时窗口边框/底部会被裁掉。

## 本工具的边界

- 只做"输入注入 + 录一块屏"，不读目标进程内存、不注入 DLL。
- 录制内容里若出现 token、账号、私人路径，按项目规则不得进 Git / 公开产物。
- **录像本身是"AI 操作"而不是"用户本人操作"**：命令和输出是真实执行结果，但鼠标移动与逐字输入是合成的。
  对外使用时不得声称是用户亲手操作，素材标签按项目证据规则单独标注。