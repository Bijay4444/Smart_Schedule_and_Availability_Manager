# Google and GitHub sign-in

Users can create a private Smart Schedule account by choosing **Continue with
Google** or **Continue with GitHub** on the existing sign-in page. A returning
provider identity signs in to the same account. Existing username/password users
can keep using their original login.

Buttons appear only when both the provider's client ID and secret are configured.
Until then, the password form works normally. Google Calendar and GitHub repository
access are not requested. This feature only authenticates users.

## What you need to configure

Create the provider applications in your own Google and GitHub accounts. Put the
credentials in the private `.env` used by Django (or the deployment bundle's `.env`
on the VM), never in source control or a chat message:

```dotenv
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
```

Either provider may be configured independently. No paid identity service was
added. Provider account eligibility and organization policies still apply.

### Exact callback URLs

| Environment | Google | GitHub |
| --- | --- | --- |
| Local `runserver` | `http://localhost:8000/accounts/google/login/callback/` | `http://localhost:8000/accounts/github/login/callback/` |
| Local Docker | `http://localhost:8080/accounts/google/login/callback/` | `http://localhost:8080/accounts/github/login/callback/` |
| Public demo | `https://schedule.khadkabijay.com.np/accounts/google/login/callback/` | `https://schedule.khadkabijay.com.np/accounts/github/login/callback/` |

Use the same hostname and port to open the app as in the registered callback.
`localhost` and `127.0.0.1` are different callback hosts. Register additional exact
callbacks if you use other ports or the original Azure hostname. Keeping separate
local and production provider apps makes configuration easier to reason about.

### Google

1. Open [Google Cloud Console](https://console.cloud.google.com/) and select/create
   a project. Open Google Auth Platform (or APIs & Services → OAuth consent screen).
2. Configure the app name, support/developer contact email, and audience. Choose
   External if people outside your Workspace organization should sign in.
3. Create an OAuth client of type **Web application**. Use the matching callback
   above as an **Authorized redirect URI**, including the trailing slash. Set the
   matching base origin if the console asks for an authorized JavaScript origin.
4. Use only identity scopes: `openid`, `email`, `profile`. No Calendar scopes or
   Calendar API enablement are needed.
5. Copy the client ID and secret into the private environment file.
6. Review Audience/publishing status before the demo. Basic identity-only scopes
   have an exception to some Testing restrictions, but other scopes or organization
   policies can restrict sign-in. Adding known demo participants as test users is
   a useful rehearsal step. For an open audience, review the Production publishing
   requirements in your actual console rather than assuming anyone can sign in.

References: [allauth Google setup](https://docs.allauth.org/en/latest/socialaccount/providers/google.html),
[Google audience and testing rules](https://support.google.com/cloud/answer/15549945).

### GitHub

1. Open GitHub → Settings → Developer settings → OAuth Apps → New OAuth App,
   or [register an OAuth App](https://github.com/settings/applications/new).
2. Name it Smart Schedule. Set Homepage URL to the base app URL, such as
   `https://schedule.khadkabijay.com.np/`.
3. Set the matching **Authorization callback URL** from the table above.
4. Register the app, generate a client secret, and copy the client ID and secret
   into the private environment file. Device flow is not needed.
5. Leave scopes limited to the configured `user:email`; no repository permissions
   are needed. Rehearse using an account other than the OAuth app owner.

Reference: [GitHub OAuth App registration](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app).

## Install, migrate, restart

For the local app:

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

The allauth dependency adds its own `account` and `socialaccount` migrations. These
were applied to the local application database during implementation. Existing
users and schedules are retained; there is no custom user-model migration.

For the public VM, rebuild and deploy the updated application image using the
existing [VM deployment workflow](azure_vm_deployment.md), preserving the existing
private database and Django credentials. Add the four OAuth values to that VM
bundle's private `.env`. The updated `compose.vm.yaml` passes them to Django.
The normal migration service applies the allauth migrations before the new web
process starts. Recreate the web container after changing credentials; restarting
an old container does not pick up Compose environment changes. Local `.env` edits
do not update the public VM. Do not regenerate the VM bundle over its existing
secrets. Live deployment was not performed as part of this change.

## Account behavior and architecture

`django-allauth[socialaccount]` implements the OAuth state validation, code
exchange, provider identity lookup, automatic username generation, signup and
session authentication. `accounts/social_auth.py` only checks provider readiness
and delegates to the library; it does not implement OAuth itself.

Provider requests start with CSRF-protected POST forms. A direct GET shows a
confirmation page rather than initiating OAuth. Callback state is validated by
allauth. Google uses PKCE. The server does not persist provider access/refresh
tokens, and no offline access is requested.

A first social sign-in automatically creates a normal non-staff account with an
unusable password and an empty schedule. The provider identity is stored so future
sign-ins find that account. It can log out using the same POST logout control.

Matching an existing email does **not** automatically link or authenticate that
existing account. A collision opens the signup-completion form with recovery
instructions. Existing users should use their original login method. Connecting
multiple providers to an existing account is outside this increment; using a
second provider with the same email is not an automatic account merge.

Emails supplied or edited on the fallback signup form are not independently
verified by this application. No SMTP-based email verification or password reset
flow is added. Authentication depends on the provider identity, not email matching.
Only the selected social routes are exposed alongside existing Django login and
logout; local password signup remains outside this feature.

## Verification and demo checklist

Automated tests mock provider transport while exercising actual state handling,
provider extraction, account creation, repeat login, session handling, cancellation,
email collisions, external redirect rejection, and disabled-provider behavior.
No real credentials or external accounts are used by those tests.

Before presenting, configure credentials and test both providers in a private
browser window. Confirm a new account gets an empty calendar, sign out, sign back
in with the same provider, and verify another account's schedule is private.
Test with your actual public hostname: this catches callback registration and
proxy HTTPS configuration mistakes that mocked tests cannot detect.

## Logout layout correction

The desktop sidebar now reserves the account footer inside the visible dynamic
viewport and scrolls navigation independently. It hides the decorative sidebar
note on short screens. This fixes the reproduced 1366×600 case where the logout
button extended below 691px. Chromium checks passed at 1366×600, 1280×480,
1440×900, 390×700 and 320×568 with Sign out inside the viewport. Login pages with
both provider buttons were inspected at laptop and phone sizes without horizontal
overflow. The fix inherits the existing green design and does not change logout's
CSRF-protected POST behavior.
