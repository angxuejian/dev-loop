# Feature: Card Draw 图标与 GitHub Pages 多页面部署

## Description

为 `card-draw` 页面增加浏览器 ICO 图标，并建立 GitHub Actions 部署流程，将 `frontend/` 下的多个独立网页统一发布到 GitHub Pages。部署后，每个包含 `index.html` 的前端子目录都按目录名获得独立访问路径，方便后续继续添加互不依赖的小型网页。

## Scope

- 为 `frontend/card-draw/` 添加与现有“星间卡藏”视觉风格一致的 `.ico` 图标，并在页面 HTML 中声明该图标，使浏览器标签页能够加载它。
- 新增 GitHub Pages 部署 workflow，在代码合入 `main` 后自动部署，并支持从 GitHub Actions 页面手动触发；使用仓库已经启用的 GitHub Actions Pages 发布源。
- 部署前安装项目依赖并构建需要编译的前端页面，确保 `card-draw` 的 TypeScript 输出包含在 Pages artifact 中；构建或打包失败时不得执行部署。
- 自动发现 `frontend/` 下包含 `index.html` 的直接子目录，将每个网页的静态文件复制到 Pages artifact 中同名目录，同时保持该网页内部的相对路径结构。
- 部署路径以仓库 Pages 根路径为基准：`frontend/card-draw/index.html` 发布到 `/dev-loop/card-draw/`，未来的 `frontend/xxa/index.html` 发布到 `/dev-loop/xxa/`；新增符合约定的目录时无需逐个修改 workflow。
- Pages artifact 不包含 TypeScript 源码、测试文件、说明文档或其他仅用于开发的文件；不得提交本地编译产物或部署产物到 Git。
- 不改变现有抽卡概率、保底规则及页面交互，也不为 Pages 根路径增加门户首页。

## Acceptance Criteria

- [ ] `frontend/card-draw/` 中有效的 ICO 文件，`index.html` 通过相对路径引用它；本地启动页面时图标请求能够成功返回。
- [ ] 仓库包含 GitHub Pages workflow，拥有部署所需的最小权限，并在 `main` 分支发生相关变更后自动运行，同时允许手动触发。
- [ ] workflow 使用 GitHub 官方 Pages artifact 上传与部署操作，且设置并发控制，避免多个 Pages 部署相互覆盖。
- [ ] 部署任务先安装依赖、构建 `card-draw` 并执行项目要求的前端检查；任一步失败时后续上传或部署步骤不会运行。
- [ ] 构建出的 Pages artifact 包含 `card-draw/index.html`、页面样式、ICO 图标以及浏览器运行所需的编译后 JavaScript，页面中的相对资源引用均能在 `/dev-loop/card-draw/` 下解析。
- [ ] 在测试目录中增加一个包含 `index.html` 和相对静态资源的示例前端目录时，打包结果自动出现同名目录且页面资源完整；移除测试目录后无需更改部署配置。
- [ ] Pages artifact 不包含 `.ts`、测试文件、Markdown 说明或本地构建目录之外的开发文件。
- [ ] 部署完成后，仓库 Pages 站点的 `/dev-loop/card-draw/` 路径能够打开抽卡页面；未来 `frontend/xxa/index.html` 按相同约定发布到 `/dev-loop/xxa/`。
- [ ] 现有抽卡专项测试、lint、格式化和类型检查保持通过，生成的构建及部署产物未被 Git 跟踪。
