# NovelTracker 配套阅读客户端

这是基于 Legado 社区源码制作的 EPUB 修复测试版，不是原作者的官方发行版。

- 基础源码：[huajideshutiao/legado](https://github.com/huajideshutiao/legado)，标签 `3.26.100113`。
- 固定提交：`c290beb185172801040ac3d4c519ec07db867ae7`。
- 修改：`legado-epubfix.patch`，包括源码及核心回归测试。
- 许可证：[GPLv3](LEGADO-LICENSE)，保留 Legado 及其依赖的原有版权和许可文件。
- 适用：支持 ARM64 的 Android 设备，最低 Android 7.0。尚未完成手机实测。

## 下载与安装

APK 和与之对应的完整源码应成对发布在 GitHub Releases，不提交 APK 到 Git 历史。
[下载测试版 APK 与对应源码](https://github.com/lzl86/novel-tracker/releases/tag/reader-epubfix-3.26.100113-test.1)。当前附件托管在贡献者 Fork，待维护者合并后可移至主项目 Releases。安装、备份迁移、签名和构建步骤见 [EPUB修复说明](EPUB修复说明.md)。

将下载的 APK 保存为 `client/legado-epubfix-arm64.apk`，运行 `python cli.py legado` 后，
手机可通过 `http://<电脑局域网IP>:5000/legado-fixed.apk` 下载。此路由要求本地已有 APK，缺失时返回 404。
`/legado.apk` 仍用于原社区发行包。

## 源码与验证

从项目根目录运行 `python scripts/prepare_reader_source.py`，脚本拉取固定社区版本并应用补丁。
生成的 `legado-source/` 被 Git 忽略，构建和测试均使用它；已有其他修改时脚本拒绝覆盖。
`reader-regression/` 直接编译该源码中的 ZIP/HTTP Range 核心及测试，避免无关 UI 依赖。

发布前运行 `python scripts/package_reader_source.py`，将其输出的完整源码压缩包与 APK 一起上传。
发布记录应包含基础版本、APK SHA-256、包名、versionCode、测试范围和源码附件。
任何签名私钥、SDK、构建缓存和个人书籍都不能随附件发布。

## 配套客户端独立更新渠道

配套修复版自 `3.26.110401debug`（versionCode 10002）起，仅检查 [lzl86/novel-tracker Releases](https://github.com/lzl86/novel-tracker/releases)。
只识别 `reader-epubfix-<三段数字版本>` 标签下的 `legado-epubfix-arm64.apk`，不跟随社区正式版/测试版设置，也不回退到社区源。
旧 `3.26.100113debug` 仍内置社区更新地址，须手动安装一次本渠道新版；保持同一包名及签名即可覆盖，无需卸载。
当前渠道沿用原测试签名以保留覆盖能力；签名私钥不提交。未来每次发布须递增 versionCode 和三段版本号，并同时发布对应完整源码。
检查失败时会报告错误；“未检测到更新”不表示手机网络一定可访问 GitHub。安装 APK 仍需用户确认。
本次渠道调整不包含同名文件导入覆盖问题的修复。

## 2026-11-04 同名书籍主动导入修复

`3.26.110402debug` / versionCode `10003` 保持独立更新渠道、原包名和签名。
从浏览器/文件管理器主动打开 EPUB 时，同名文件不再仅按修改时间判断是否覆盖。
输入先落到应用缓存，再以截断写入方式覆盖书籍保存位置；即使源与目标为同一文件，也不会先截断输入。
空输入或读取失败会保留原文件，结束时清理临时文件。目标写入阶段失败仍可能留下不完整文件，应重新导入；系统文件提供方无法统一保证原子替换。
沿用原有同路径书籍记录、解析句柄/缓存清理和目录刷新逻辑；覆盖到相同保存 URI 时保留书籍记录。不同 URI 或浏览器另存“(1)”后缀不保证合并书籍。
本次只针对浏览器/文件管理器的文件关联导入路径；外部书库的其他下载入口行为不在本次验证范围内。

## 云端更新入口（3.26.110403debug / versionCode 10004）

检查更新：https://logicnexus.icu/reader/releases.json
下载及源码：https://logicnexus.icu/reader/
GitHub Releases 继续作为源码与发行附件备份。手机的检查及下载不依赖 GitHub API，不回退到社区。
新旧版本保持同一包名和签名，可覆盖安装。旧版需要手动安装一次云渠道版，之后使用关于页检查更新。
JSON 沿用 GithubRelease 字段格式，专用标签与数字版本、ARM64 安装包筛选仍然生效。
发布必须先上传版本目录内 APK、完整源码及 SHA256SUMS 并验证，再原子替换 releases.json 和首页，禁止覆盖已发布版本的 APK。
HTTPS 证书由 certbot 签发；自动续期需另行验证；Nginx 提供静态文件与 Range 下载。只分发客户端，无个人书籍或签名密钥。

当前部署状态：DNS-01 证书已签发，2027-02-02 到期。公网443尚待安全组放行；自动续期尚未验证通过。确认公网HTTPS和续期方案前，不发布云端版本到GitHub，也不替换本地稳定下载包。
