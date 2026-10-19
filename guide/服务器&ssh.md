换到新实例：按 [新服务器重新部署.md](./新服务器重新部署.md) 全量复现。SSH 端口每次开机可能变化，以控制台为准，不要写进业务代码。

## 服务器1

### 服务器信息

| 项 | 值 |
|----|----|
| GPU | RTX 5090 32GB |
| ComfyUI | `0.0.0.0:8188`，路径 `/root/autodl-tmp/ComfyUI`（0.33.0） |
| 模型 | MiniMax H3（fl2va/ref2va int8 + qwen3vl + video/audio VAE + turbo 4step LoRA） |
| 图 | 无 Flux / Wan 文生图权重 |

### 登陆信息
ssh -p 30856 root@connect.westc.seetacloud.com

密码：
wpIXcB0vYeDF

隧道：

```bash
ssh -L 8188:127.0.0.1:8188 -p 30856 root@connect.westc.seetacloud.com
```


## 服务器2


ssh -p 16659 root@connect.westd.seetacloud.com
密码：xmrYP2wSgKzz