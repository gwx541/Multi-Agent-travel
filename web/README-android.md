# 安卓 App 构建与安装说明

本项目的安卓 App 由 [Capacitor](https://capacitorjs.com/) 把现有的 React 前端（`web/`）打包成原生壳，复用全部前端代码，并额外提供：

- 原生 GPS **实时定位**（`@capacitor/geolocation`），无定位权限时自动回退到 IP 粗定位。
- 外链**跳转小红书 / 携程等 App**：聊天里的链接会交给系统打开，已安装对应 App 时由 App 接管，否则用系统浏览器。
- App 内**「服务器」按钮**：首次使用填入后端地址即可连接。

已构建产物（调试版 APK）：

```
web/android/app/build/outputs/apk/debug/app-debug.apk   (约 4.7 MB)
```

---

## 一、直接安装已构建的 APK（最快）

1. 用数据线把手机连到电脑，或把 `app-debug.apk` 传到手机（微信/QQ/U 盘均可）。
2. 在手机上点开 APK 安装；首次会提示「允许安装未知来源应用」，同意即可。
3. 也可以用 adb 安装（手机需开启「USB 调试」）：

```powershell
D:\Android\Sdk\platform-tools\adb.exe install -r "D:\Python\trave\travelagent\web\android\app\build\outputs\apk\debug\app-debug.apk"
```

---

## 二、连接后端（重要）

App 是「前端壳」，聊天、记忆等功能都要连后端。后端默认只监听 `127.0.0.1`，**手机连不上**，需要让它监听局域网。

1. 让电脑和手机连**同一个 WiFi**。

2. 查看电脑局域网 IP（PowerShell）：

```powershell
ipconfig   # 找到 IPv4 地址，例如 192.168.1.23
```

3. 用 `0.0.0.0` 启动后端（在项目根目录，已装好 Python 依赖）：

```powershell
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

4. 打开 App → 点右上角 **「服务器」** 按钮 → 填入 `http://你的电脑IP:8000`（例如 `http://192.168.1.23:8000`）→ 确定，App 会自动重载并连接。

> 提示：调试版 APK 已允许明文 HTTP（`cleartext`），所以可以直接用 `http://`。正式发布时建议改用 HTTPS。

---

## 三、本地记忆（重要）

从该版本起，**记忆全部保存在手机本地**，后端不再存任何记忆，App 也**不需要登录**：

- **存什么**：长期偏好（如「不吃辣」）+ 全部会话历史，都写在一个文件里。
- **存哪里**：开启「所有文件访问」后保存到 `存储/TravelAgent/memory.json`。
  - **卸载 App 后该文件仍保留**；重装 App 会自动读回长期记忆。
  - **换手机**：把这个 `memory.json` 拷到新手机的同名目录 `存储/TravelAgent/` 下，再装 App 即可继承全部记忆。
- **怎么开启**：首次进入会提示，点右上角「**存储授权**」→ 系统设置页里打开「允许所有文件访问」→ 返回 App 再点一次「存储授权」即可。未授权时记忆暂存于 App 内部（卸载会丢）。
- **查看记忆**：点右上角「**记忆**」可查看已记住的长期偏好。
- 会话时，App 会把「长期偏好 + 近期上下文」随请求发给模型作为上下文；模型识别到的新偏好会回传并自动存到本地文件。

> 浏览器（开发）模式下没有文件权限，记忆退化保存在浏览器 `localStorage`。

## 四、权限与跳转说明

- **定位**：首次需要定位时，系统会弹权限申请，选「允许」。拒绝则自动使用 IP 粗定位（精度较低）。
- **跳转小红书 / 酒店**：聊天结果里的链接点击后由系统处理；装了小红书/携程 App 会询问用 App 打开。已在 `AndroidManifest.xml` 的 `<queries>` 声明了 `xhsdiscover`、`ctrip`、`http(s)` 方案（Android 11+ 必需）。
- **存储**：`MANAGE_EXTERNAL_STORAGE`（所有文件访问），用于把记忆持久化到公共目录。

---

## 五、修改前端后重新打包

每次改了 `web/` 的前端代码，需要重新构建并同步到安卓工程再打包。

构建环境（本机已配置好）：

| 工具 | 路径 / 版本 |
| --- | --- |
| JDK | `D:\Java\jdk-21`（JDK 21，Capacitor 8 必需） |
| Android SDK | `D:\Android\Sdk`（platform-tools、platforms;android-36、build-tools 35.0.0 / 36.0.0） |
| 环境变量 | `JAVA_HOME=D:\Java\jdk-21`、`ANDROID_HOME=D:\Android\Sdk` |

一键打包（在 `web/` 目录）：

```powershell
npm run android:apk
```

该命令等价于：构建前端 → `cap sync android` → `gradlew assembleDebug --init-script cn-mirror.init.gradle`。

> `cn-mirror.init.gradle` 把 Gradle 依赖仓库换成阿里云镜像，`gradle-wrapper.properties` 用腾讯云镜像下载 Gradle，解决国内 `dl.google.com` 超时问题。

如果环境变量没生效（新开终端），可在打包前手动设置：

```powershell
$env:JAVA_HOME = "D:\Java\jdk-21"
$env:ANDROID_HOME = "D:\Android\Sdk"
$env:ANDROID_SDK_ROOT = "D:\Android\Sdk"
```

---

## 六、生成正式签名包（可选）

调试 APK 仅用于测试。要上架或长期安装，建议生成签名的 release 包：

```powershell
# 1. 生成签名 keystore（只需一次）
D:\Java\jdk-21\bin\keytool.exe -genkey -v -keystore travelagent.keystore -alias travelagent -keyalg RSA -keysize 2048 -validity 10000

# 2. 在 android/app/build.gradle 配置 signingConfigs 后执行
cd android
.\gradlew.bat assembleRelease --init-script cn-mirror.init.gradle
```

---

## 七、常见问题

- **App 一直转圈 / 连不上**：检查后端是否用 `--host 0.0.0.0` 启动、手机电脑是否同一 WiFi、「服务器」地址是否填对、电脑防火墙是否放行 8000 端口。
- **记忆没保存到公共目录 / 卸载后丢了**：说明没开「所有文件访问」。点「存储授权」在系统设置里打开，返回后再点一次。
- **换机后记忆没继承**：确认把旧机 `存储/TravelAgent/memory.json` 拷到新机**同名目录**，且新机已开「所有文件访问」。
- **定位失败**：在系统设置里给 App 授予定位权限并打开手机定位开关；否则会回退到 IP 粗定位。
- **构建报 `Failed to find Build Tools` / 找不到 SDK**：确认 `android/local.properties` 里 `sdk.dir=D\:\\Android\\Sdk` 正确，且对应 build-tools 已安装。
- **构建报缺少 JDK 21 工具链**：确认 `JAVA_HOME` 指向 `D:\Java\jdk-21`。
