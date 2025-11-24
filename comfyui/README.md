# Zernet ComfyUI

Create the directories `models`, `extensions` and `workflows`


`models/` - copied to `ComfyUI/models/`


`extensions/` - copied to `ComfyUI/custom_nodes/`


`workflows/` - copied to `ComfyUI/user/default/workflows/`

To add HTTP basic auth use BASIC_AUTH env var with a <user>:<hash> htpasswd string.

Listens on 8188, or 5000 when BASIC_AUTH is used.