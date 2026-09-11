---
name: git_workflow
description: git 规范:先看状态,小步提交,分支合并
---
# git 流程
1. 操作前先 git status / git diff 了解现状
2. 若未初始化先 git init;提示缺身份则 git config user.name/user.email
3. 小步提交:一次一个逻辑变更,消息简洁明确
4. 新功能用分支:git checkout -b feature/xxx,完成后再合并
5. 合并:git checkout main && git merge feature/xxx
6. 用 git log --oneline 确认提交历史符合预期
