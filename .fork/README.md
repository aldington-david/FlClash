# FlClash AnyTLS REALITY

本仓库发布独立 Android 应用，包名为 `com.github.aldingtondavid.flclash`，显示名为 **FlClash AnyTLS REALITY**。它与官方应用共存，使用本仓库自己的固定签名，不可覆盖安装官方 APK。

每小时第 47 分钟检查 `chen08209/FlClash` 与 `aldington-david/mihomo` 最新正式 Release。任一正式版本更新后，固定双方 tag 和 commit，构建且仅发布 `FlClash-版本-android-arm64-v8a.apk`；另外提供校验和、签名证书摘要与来源记录。GitHub 计划任务可能延迟，也可以手动执行 Actions。

FlClash 需要自有 Go API，因此在本仓库用户版 mihomo 正式 tag 上叠加该 FlClash 版本原有的兼容补丁。补丁来自上游对应 submodule commit，而不是取未固定的分支。当前上游使用单个 `feat: support FlClash` commit 承载兼容代码；若布局改变、补丁冲突、Go 测试或 Android 构建失败，Actions 会停止发布，需审查适配。

维护分支为 `anytls-reality`。每个 Release tag 为 `应用tag-anytls-核心tag`；tag 保存完整应用源码、核心 gitlink、兼容 patch 及 `.fork/provenance.json`。失败的构建可以重新运行，继续使用同一源码 tag。正式 Release 只在签名、包名、ABI 检查通过并上传完全部文件后公开。Android versionCode 使用 `1000000000 + 首次准备该版本的 Actions run_number`，同一应用版本也能接收核心更新。

手工复现须检出某个发布 tag，执行 `git submodule update --init`，然后执行 `git -C core/Clash.Meta apply ../../.fork/flclash-compat.patch`，再按对应 workflow 的 Go/Flutter/NDK 版本构建。维护分支保存自动化和改动模板，不能直接视作已经集成对应核心的发布源码。

仓库需要四个 GitHub Actions Secrets：`KEYSTORE`（PKCS12 文件的 base64）、`STORE_PASSWORD`、`KEY_ALIAS`、`KEY_PASSWORD`。固定签名须备份；丢失后无法升级已安装的独立应用。构建显式指定 `PKCS12`，临时文件名沿用上游 `keystore.jks`。缺少签名配置时构建失败，不回退 debug 签名。

另需仓库变量 `ANDROID_CERTIFICATE_SHA256`，其值为签名证书 SHA-256 的 64 位十六进制串。发布前比较实际 APK 的签名证书指纹，变量为空或不一致时停止发布。

`android/gradle.properties` 使用 Flutter 的 `force-version-code-ignoring-abi=true`，关闭拆分 APK 时默认增加的 ABI 编号偏移，使已安装应用与 Release 正文使用同一个 versionCode。`BUILD-PROVENANCE.json` 同时记录实际源码提交、执行 workflow 的提交及 Actions run URL。这里只固定源码与构建参数，不承诺重新打包后的字节完全一致。

此独立版本移除了 Firebase 构建插件和 Android 统计依赖，不需要上游的 `SERVICE_JSON`。更新检查指向本仓库，通过 Release 正文中 `Android version code:` 的数值识别包括核心更新在内的新构建。

定制分为两类：签名、运行时行为仍使用严格的 `app.patch`；仓库和核心链接使用校验出现次数的字面量替换，不依赖“关于”页组件布局。`firebase-native-symbols.patch` 仅在上游加入对应 Crashlytics 构建功能时应用，移除导入、扩展配置和上传任务；不改动普通原生调试符号处理。`overlay.py` 在创建源码标签前检查所有已跟踪 Android 构建脚本与运行时源码，发现未知 Firebase 入口立即停止；APK 打包后另查 releaseRuntimeClasspath，防止统计 SDK 从其他依赖重新引入。

扫码的 ML Kit 依赖链使用 Firebase 的基础 annotations/components/encoders 库，原 v0.8.98 APK 也包含这些基础库。运行时检查只放行这组明确的基础依赖，不全局排除它们，以免破坏扫码；Crashlytics、Analytics、Google measurement 和其他新出现的 Firebase SDK 均拒绝发布。这里的“禁用 Firebase”沿用本 fork 原有的含义：不初始化 Firebase，不加载统计/崩溃上报 SDK，不运行相应构建插件或上传任务。

`.fork/provenance.json` 记录定制文件的规范化文本指纹 `overlay_sha256`。未发布标签若由旧版定制生成，重跑会明确拒绝复用；需先备份并重建该未发布标签。已公开 Release 只检查资产完整性，不因定制更新而重写；上传前也会再次检查仍为草稿。结构性上游改动仍可能需要人工适配，流程不会模糊匹配或忽略补丁错误。

`python .fork/test_overlay.py --ref upstream/v0.8.98 --ref upstream/v0.8.99` 可在具备对应上游 Git 引用的维护 checkout 中，回放两版真实源码并检查缺失/重复链接和新增 Firebase 入口的拒绝行为。Windows 运行时将 `TEMP`、`TMP` 指向工作区内的临时目录。CI 还运行 Flutter 分析、相关测试和原有 Go/Android 编译检查。

维护 checkout 超过 30 天无提交时，计划任务创建一次空提交，保持公开仓库的计划任务活跃。不会把上游开发分支当正式发布源。升级所需 Flutter、Go、NDK 版本读取自对应上游正式 tag 的 workflow。

本地已通过 v1.19.32 + FlClash v0.8.98 兼容补丁的完整 Go wrapper 测试；最终 Android CGO、Flutter 构建、APK 签名与 ABI 检查由 Actions 执行。`python .fork/prepare.py --self-test` 可执行同步脚本的最小输入检查。
