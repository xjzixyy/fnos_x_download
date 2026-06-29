# x下载

一个本地 Python HTTP 服务，用 `twittervideodownloader.com` 的下载页提取 X/Twitter 视频直链，也可以解析 X/Twitter 图片原图，并保存到本机目录。

## 启动

```bash
python3 main.py
```

默认地址：

```text
http://127.0.0.1:8765
```

## 使用

打开页面后粘贴 X/Twitter 图片或视频链接，点击“加入队列”。服务会在后台并发处理队列，自动提取并下载最高分辨率视频或图片原图。

多图推文会自动展开为多个下载任务。队列卡片会显示缩略图；视频缩略图来自解析页，图片缩略图来自 X/Twitter 图片地址。队列状态会保存到文件，服务重启后会恢复；重启前处于“下载中/停止中”的任务会恢复为“排队中”。排队中或下载中的任务可以手动停止，失败或已停止的任务可以重新加入队列。

## 下载目录

基础下载地址可以在页面左侧下方修改，页面会在浏览器本地记住上一次输入。服务会自动在该目录下创建日期子目录，例如：

```text
/vol1/1000/downloads/xdownload/20260609
```

端口默认是 `8765`，也可以用环境变量调整：

```bash
XDOWNLOAD_DOWNLOAD_DIR=/vol1/1000/downloads/xdownload XDOWNLOAD_PORT=8899 python3 main.py
```

常用环境变量：

```text
XDOWNLOAD_DOWNLOAD_DIR           页面默认下载根目录
XDOWNLOAD_QUEUE_FILE             队列文件路径
XDOWNLOAD_MAX_CONCURRENCY        并发下载数，默认 2
XDOWNLOAD_TASK_TIMEOUT_SECONDS   单任务超时秒数，默认 1800
XDOWNLOAD_PORT                   服务端口，默认 8765
```

## 测试

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile main.py xdownload/__init__.py xdownload/config.py xdownload/extractor.py xdownload/downloader.py xdownload/server.py
```

## 飞牛打包

在飞牛机器上拉取或更新 Git 仓库后构建：

```bash
git pull
./scripts/build_fnos_native_fpk.sh
```

输出：

```text
dist/fnos-native/xdownload.fpk
```
