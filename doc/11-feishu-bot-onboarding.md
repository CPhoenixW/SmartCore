# Feishu bot onboarding boundary

## Current production contract

SmartCore currently runs one server-managed Feishu application. A `feishuBot`
pairing does not install or discover an arbitrary Feishu bot: it binds the
current user's Feishu account to the already configured application.

To pair it, create a Feishu bot pairing request in the Device page and send
`绑定 <配对码>` to the SmartCore bot in a one-to-one chat. Then confirm the
claimed request in the workbench.

## Adding another bot application

Adding a separate Feishu application is an administrator deployment task.
It needs its own `appId`, `appSecret`, verification token, encryption key and
a dedicated event callback route. Those values must stay in the server's
secret configuration; a normal device-pairing form must never collect or
render them.

Multi-application support should be introduced as a separate change with:

1. an administrator-only encrypted bot-connection store;
2. a callback route that resolves the target bot before request validation;
3. a bot identifier on both `LifeDevice` and `LifeIdentity` so outgoing
   notifications use the same application that received the binding;
4. per-bot health checks and credential rotation.

Until that work is complete, the UI must describe Feishu pairing as binding
the configured SmartCore bot, rather than implying that any bot can pair.
