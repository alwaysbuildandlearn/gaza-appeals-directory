# Gaza Appeals

A local fundraising directory using Python 3.12 and SQLite. It has no external dependencies.

## Run

Run `python app.py` and open http://127.0.0.1:8765/. The terminal prints a temporary reviewer password. To choose a stable password, set APPEALS_ADMIN_PASSWORD before starting the program.

The first run adds 26 fictional appeals. They have no payment links. To run an empty directory, set APPEALS_DEMO=0 before the first run with a fresh database. The public submission form accepts Chuffed and GoFundMe links. Sign in at /review, review the submitted campaign, and set its status to Active to publish it. Set it to Paused to take it down. The form's contact email stays in the reviewer interface.

The homepage returns 20 appeals per page. Search and category filters apply before pagination. Ranking uses the manually recorded USD total for the 35 days ending on the entered check date, smallest first. A total checked more than seven days ago or missing a date/amount is placed after ranked totals. A recorded zero is a valid total. Ties use listing ID. Amounts are manual snapshots and are not updated automatically.

This server binds to localhost. Before public deployment, move it behind a production-grade HTTP application stack with HTTPS, secure cookies, persistent storage and backups, and rate limiting for submissions and reviewer sign-in. Keep the database out of Git and keep reviewer credentials out of the source.

## GitHub

Intended owner: https://github.com/alwaysbuildandlearn. Create a private repository from that account and set repository-local `user.name` and `user.email` before the first commit. Use that account's GitHub noreply address if you want to keep your personal email private.

