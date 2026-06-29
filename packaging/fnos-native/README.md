# xdownload 飞牛原生 Python 打包骨架

这个目录用于生成不依赖 Docker 的飞牛 `fpk` 应用包。安装后服务通过系统 Python3 启动：

```text
/usr/bin/python3 <应用安装目录>/app/main.py
```

默认端口是 `8765`。页面左侧下方可以修改基础下载地址，服务会自动在该目录下创建 `YYYYMMDD` 子目录。`XDOWNLOAD_DOWNLOAD_DIR` 只作为页面默认值。

默认并发数是 `2`，单任务超时是 `1800` 秒。队列保存到 `/var/apps/xdownload/data/queue.json`，服务重启后会恢复队列。

`ICON.PNG` 和 `ICON_256.PNG` 必须放在 fnpack 工程根目录，打包脚本会自动复制。

在飞牛机器上构建：

```bash
./scripts/build_fnos_native_fpk.sh
```

生成结果位于：

```text
dist/fnos-native/xdownload.fpk
```

后续更新时，把仓库推到 Git，然后在飞牛机器上 `git pull` 后执行 `./scripts/build_fnos_native_fpk.sh`。

如果安装后没有自动启动，可以 SSH 执行：

```bash
sudo /var/apps/xdownload/cmd/main start
sudo systemctl status xdownload.service
```

导入本包内置的恢复链接：

```bash
sudo /var/apps/xdownload/target/bin/recover-queue.sh
sudo systemctl restart xdownload.service
```
