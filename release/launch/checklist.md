# 发布检查清单(v1.0.0)

> 状态用 ✅ / ⬜。发布前逐项过一遍。账户注册好之前,先把 1–4 全部就位。

## 1. 产物
- [ ] 桌面安装包已是最新:英文 `Hummingbird-v1.0.0-EN-Setup.exe`(247MB,含离线语音模型)
- [ ] 中文安装包已是最新:`蜂鸟-v1.0.0-中文安装包.exe`
- [ ] 双击启动:窗口默认最大化、所有功能区露出、底部 Ollama 状态灯亮绿
- [ ] 语音按钮可用(安装包自带 STT 模型)

## 2. 仓库(GitHub hAcKlyc/MyAgents)
- [ ] 上传源码目录(ollama_agent.py / agent_gui.py / installer.py / AGENTS.md / LICENSE / RELEASE_NOTES.md / bench/ / design/ / research/)
- [ ] 替换 README 为 `release/github/README.md`(EN,含截图链接)
- [ ] 添加 `release/github/README_zh.md`(中文)
- [ ] 上传截图: `screenshot-*.png`(全图)+ `preview-*.png`(社交预览 1280×640)
- [ ] 加 `.gitignore`(`dist/`、`build/`、`*.spec`、`release/_screenshot*`)

## 3. Release
- [ ] 建 tag `v1.0.0`
- [ ] Release 正文 = `RELEASE_NOTES.md`(已含)
- [ ] 附件:两个安装包 + 截图(注意 GitHub 单文件限 2GB,247MB 没问题)
- [ ] Release 封面图 = `preview-en.png`

## 4. 素材核对
- [ ] 截图无个人隐私信息(工作目录路径、会话内容)
- [ ] 发布稿链接均为最终地址(repo + release 页)
- [ ] 安装包命名对国际用户清晰(EN 包名明确带 EN)

## 5. 发布顺序(推荐)
1. **GitHub Release** 先行(所有链接的锚点)
2. **HN Show HN**(美东上午 ≈ 北京时间 23:00)
3. **Reddit r/LocalLLaMA**(与 HN 错开数小时)
4. **Product Hunt**(美西周二–周四上午)
5. **r/selfhosted**(再隔 24h)
6. **B站视频**(中文社区,可晚几天,先剪 40s 竖版预告)
7. 知乎回答 / 少数派投稿(如果注册了)

## 6. 发布后 48h
- [ ] 回复所有 HN/Reddit 评论(回复率高 = 排名高)
- [ ] 记录各渠道流量数字,回来更新 memory
- [ ] 收集 3–5 条真实反馈 → 定 v1.1 迭代方向

## 7. 注意
- 发布属于**对外提交**:每步发布前先给用户过目发布稿。
- 不要在评论里泄露个人隐私(电脑型号、照片文件等已在素材中打了码就保持)。
