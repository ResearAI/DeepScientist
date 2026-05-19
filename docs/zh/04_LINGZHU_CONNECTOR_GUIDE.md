# 04 Lingzhu 连接器指南：把 Rokid Glasses 绑定到 DeepScientist

Lingzhu 现在是一个极简的一步式绑定流程。

DeepScientist 会直接在自己的 daemon / Web 端口上提供 Lingzhu 兼容路由：

- `GET /metis/agent/api/health`
- `POST /metis/agent/api/sse`

真实设备要想接入，Rokid 平台里填写的地址必须就是外部可以访问到的 DeepScientist 公网地址，不能是 `127.0.0.1`、`localhost` 或私网地址。

参考：

- Rokid 开发者论坛：https://forum.rokid.com/post/detail/2831
- Rokid 智能体平台：https://agent-develop.rokid.com/space

## 1. 绑定前提

先确认：

- DeepScientist 已正常启动
- 你当前打开的 DeepScientist 网页地址就是最终对外可访问的公网地址
- 如果当前网页地址是本地地址或私网地址，Lingzhu 不应直接保存

## 2. 页面里现在保留什么

`Settings > Connectors > Lingzhu` 现在只保留必要内容：

- 一个 `Add Lingzhu (Rokid Glasses)` 入口
- Rokid 平台创建表单截图
- 自动生成的可复制字段
- 中文绑定指引
- 保存按钮

不再要求你先手动改 host、port、agent、OpenClaw 配置片段或额外调试步骤。

## 3. 点击后会自动生成什么

点击 `Add Lingzhu (Rokid Glasses)` 后，弹窗会自动显示这些值，并且每一项都可以直接复制：

- 自定义智能体ID
- 自定义智能体url
- 自定义智能体AK
- 智能体名称
- 类别
- 功能介绍
- 开场白
- 入参类型
- 图标 PNG 地址

其中：

- `Custom agent URL` 会自动生成成 `https://<你的公网地址>/metis/agent/api/sse`
- `AK` 会自动随机生成，并在保存后长期复用，不会每次都变
- logo 使用 DeepScientist 的 PNG 资源，方便直接上传到 Rokid

![Rokid 平台创建三方智能体](../images/lingzhu/rokid-agent-platform-create.png)

## 4. 用户怎么做

在 Rokid 平台：

1. 打开 `项目开发 -> 三方智能体 -> 创建`
2. 选择“自定义智能体”
3. 把弹窗里自动生成的字段逐项复制过去
4. 图标上传 DeepScientist PNG logo
5. Rokid 表单填写完成后，回到 DeepScientist 点击保存

保存完成后，Lingzhu 绑定就算完成。

## 5. 后续怎么用

眼镜侧后续只需要请求：

- `POST /metis/agent/api/sse`

并带上：

- `Authorization: Bearer <保存后的AK>`

使用规则：

- 新任务必须以 `我现在的任务是 ...` 开头
- 只有这个前缀后面的正文才会被当成新的 DeepScientist 任务
- 如果只是想继续拿中间进展，不要重复这个前缀，直接说 `找DeepScientist` 或 `继续`

如果你同时跑多个 quest，Lingzhu 更适合快速创建或查看关键进展，不适合当多任务总控台。多任务入口选择见 [34 多任务入口选择](./34_MULTITASK_ORCHESTRATION_GUIDE.md)。

## 6. 常见问题

### 为什么不能用 `127.0.0.1`

因为 Rokid 平台和外部设备访问不到你的本地回环地址。Lingzhu 只应该注册公网地址。

### 为什么要自动生成 `AK`

因为 `AK` 本质上就是这个外部接入口的 Bearer 密钥。系统生成并持久化，比手填更稳定，也更不容易出错。

### 保存后还需要再手动配很多参数吗

不需要。Lingzhu 现在的目标就是让用户只看到必要字段，复制过去，然后保存完成。
