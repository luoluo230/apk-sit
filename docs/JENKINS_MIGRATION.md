# 将 jenkins-clone 迁入 apk-site（复制即用）

## 1. 复制即用（推荐）

1. **把 jenkins-clone 复制到 apk-site 目录下**
   ```bash
   cd /path/to/apk-site
   cp -r /path/to/jenkins-clone ./jenkins-clone
   ```

2. **启动 apk-site**
   ```bash
   ./start.sh
   ```
   启动时会自动：
   - 在 `jenkins-clone/.apk-site-env` 写入当前 `APK_DIR`、`JENKINS_CLONE`、`JENKINS_JOB_DIR`
   - 用 `jenkins-clone-overlay/` 下的脚本与 Job 配置覆盖到 `jenkins-clone/`，使路径与当前环境一致（无需再改路径）

3. **（可选）放 jenkins.war 供「Jenkins 管理」多实例**
   - 将 [jenkins.war](https://get.jenkins.io/war-stable/latest/jenkins.war) 放到 `apk-site/jenkins-clone/jenkins.war`
   - 或设置环境变量 `JENKINS_WAR_PATH` 指向 war 路径

4. **使用 Jenkins**
   - 用原方式启动 Jenkins 时，将 `JENKINS_HOME` 设为 `apk-site/jenkins-clone`
   - 或在管理中心「Jenkins 管理」页按端口启动新实例（需已配置 war）

**无需再执行** `scripts/update_jenkins_paths.py`，overlay 已包含可移植脚本与配置。

## 2. 路径说明

- **apk-site 默认**
  - Jenkins 构建目录：`apk-site/jenkins-clone/jobs/Android/builds`
  - War 候选：`apk-site/jenkins-clone/jenkins.war` 或 `apk-site/data/jenkins_instances/jenkins.war`

- **未迁入时**  
  在 `.env` 中设置 `JENKINS_BUILDS_DIR`、`JENKINS_WAR_PATH` 指向当前机器路径即可。

## 3. 仅想改路径、不覆盖脚本时

若你保留 jenkins-clone 内自己的脚本，只希望把旧绝对路径替换成当前环境，可手动执行：

```bash
python scripts/update_jenkins_paths.py          # 执行替换
python scripts/update_jenkins_paths.py --dry-run # 仅预览
```
