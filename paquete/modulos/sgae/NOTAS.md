# Module «sgae»

**What it does.** For members of SGAE (Spanish collecting society). It opens a separate Chrome window (own profile, debugging port 9223)
where the user logs in to the SGAE web office; the module then reads what the logged-in web page itself requests and shows three lists:
registered works (validated), in process (pending / rejected) and works ready to register from the user's folders.

**Privacy.** The password is typed only in the SGAE window and never reaches the manager. The session token lives in memory only and is never
written to disk or sent to the UI. What is stored: `datos/modulos/sgae/memoria.json` (the works list the user already has at SGAE). Nothing leaves the
computer except calls to SGAE's own servers, with the user's own session.

**Conventions.** Works ready to register: `<library>/SGAE-REGISTRO MUSICAL/<album>/SGAE enviado/<Title> audio <Artist>.mp3` and `<Title> letra <Artist>.txt`
(the artist is taken from the configuration).

**Limits.** This is not an official SGAE tool. The SGAE web office can change and break it; use it at your own risk and responsibility.
The registration form replay (`enviar`) must always be confirmed by the user.
