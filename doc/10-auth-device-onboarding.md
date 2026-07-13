# Account And Device Onboarding

## Acceptance

1. A visitor can register with a unique login name and password. Registered users always receive the user role.
2. The default account remains the administrator setup path; registration never modifies it.
3. A Feishu bot pairing is claimed only by the command binding plus the pairing code sent from the Feishu account being bound. The workbench must still confirm it before activation.
4. A screen opens a one-time pairing URL, claims the request, waits for workbench confirmation, then stores its device id and token locally. Its WebSocket connection is rejected without the matching credential.
5. Pi photo polling, upload, and failure reports accept only the paired device token and matching device id. The retired global device token is not used.
