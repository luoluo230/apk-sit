# jenkins-clone 项目说明

## 目录是啥

- 当前目录 = **JENKINS_HOME**（配置、任务、构建历史等）
- `jobs/Android/`：Android 构建任务，apk-site 的「构建管理」会调这个任务
- `war/`：Jenkins 的 war 解压内容（没有单独的 `jenkins.war` 文件）

## 要不要启动服务？要，且是「Jenkins 本身」

- **需要单独启动的是 Jenkins 服务**（Java 进程），否则 apk-site 无法触发构建、也拉不到日志。
- 项目里**没有**“一键启动 Jenkins”的脚本（只有 `start_jenkins.sh` 的模板说明，需自备 `jenkins.war` 或指定路径）。
- `start_service.sh` 启动的是 **APK 下载用 HTTP 服务（端口 8888）**，不是 Jenkins。

## 端口号

- **Jenkins 默认端口：8080**  
  用官方方式启动（`java -jar jenkins.war`）且不指定 `--httpPort` 时，就是 **8080**。
- 若你启动时指定了其他端口（例如 `--httpPort=9090`），则：
  - 启动 Jenkins 时用该端口；
  - 在 **apk-site** 里设置相同端口，例如：  
    `export JENKINS_PORT=9090` 再启动 apk-site。

## 如何启动 Jenkins（端口 8080）

在终端执行（需已安装 Java，且本目录为 JENKINS_HOME）：

```bash
cd /path/to/apk-site/jenkins-clone
export JENKINS_HOME=/path/to/apk-site/jenkins-clone
java -jar /path/to/jenkins.war --httpPort=8080
```

把 `/path/to/jenkins.war` 换成你本机 jenkins.war 的路径；若用其他端口，把 `8080` 改成该端口，并在 apk-site 里设 `JENKINS_PORT`。

## 和 apk-site 的关系

- apk-site 的「构建管理」会请求：`http://localhost:<JENKINS_PORT>/job/Android/...`（默认 8080）。
- 所以：**Jenkins 必须先在本机以对应端口启动**，否则会一直显示「无法连接 Jenkins」或「构建日志尚未生成」。

## 若 apk-site 触发构建报 403

- 原因：Jenkins 开了安全或 CSRF，apk-site 无法无认证触发。
- **推荐做法（无需账号）：**
  1. 停掉 Jenkins 进程。
  2. 在 **jenkins-clone** 目录执行：`chmod +x fix_apksite_403.sh && ./fix_apksite_403.sh`
  3. 再启动 Jenkins（如 `./start_jenkins.sh`）。
- 脚本会把 `config.xml` 设为 useSecurity=false 并去掉 crumbIssuer，**之后必须重新启动 Jenkins** 才生效。若以后 Jenkins 自己把配置改回去，再跑一次脚本即可。
- 仅建议在内网或本机使用。
