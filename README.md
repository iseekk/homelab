# Homelab - Private Raspberry Pi Server

This project is a fully isolated, secure home server running on a Raspberry Pi (ARM64 architecture). The core of the system is the **Vaultwarden** password manager, which is completely hidden from both public and local networks using the **Tailscale** mesh network.

The Vaultwarden container shares the network stack directly with Tailscale (`network_mode: "service:tailscale"`). This means the service is completely invisible on your local network and can only be accessed after authenticating within your private Tailnet.

## 📂 Project Structure

This is how the directory structure should look in your main folder (e.g., on an SSD mounted to your Raspberry Pi):

```text
~/homelab/
├── docker-compose.yml    # Main services definition
├── .env                  # (NOT TRACKED IN GIT) Actual environment variables and keys
├── .env-example          # Environment variables template
├── README.md             # Project documentation
├── scheduler/            # Vaultwarden backup scheduler service (Docker image built locally)
├── backups/              # Local backup destination (created automatically)
├── ts-data/              # Tailscale state (prevents duplicate devices on restart)
└── vw-data/              # Main Vaultwarden database (db.sqlite3) and keys
```

## 🚀 Deployment (First Run & HTTPS Setup)

1. **Prepare the environment:** Ensure you have Docker and the Docker Compose plugin installed on your Raspberry Pi.

2. **Clone the files:** Place the `docker-compose.yml` file into the `~/homelab/` directory.

3. **Environment setup:** Copy the environment variables template:
   ```bash
   cp .env-example .env
   ```

4. **Generate Tailscale Auth Key:**
   1. Log in to the Tailscale Admin Console.
   2. Navigate to _Settings_ -> _Keys_ and generate a one-time Auth Key.
   3. Open the `.env` file (e.g., `nano .env`) and paste the key into the `TS_AUTHKEY` variable.

5. **Start the server:** Spin up the containers in detached mode:
   ```bash
   docker compose up -d
   ```
   Check your Tailscale Admin Console to verify that the new machine named `homelab` is active and connected.

6. **Configure HTTPS (Tailscale Serve):** Vaultwarden shares the network stack with Tailscale, meaning it is visible to the VPN container on the local port 80. To enable HTTPS, configure the `tailscale serve` feature inside the running container by executing:
   ```bash
   docker exec -it tailscale tailscale serve --bg 80
   ```
   > **Note:** This configuration is automatically saved inside the mounted `./ts-data` directory, so it will persist across Raspberry Pi reboots.

7. **Get your secure URL:** To find your private, secure HTTPS URL with a valid SSL certificate, run:
   ```bash
   docker exec -it tailscale tailscale serve status
   ```
   The console will output your generated address (e.g., `https://homelab.your-tailnet.ts.net`).

8. **User Registration & Hardening:**
   1. Ensure Tailscale is running on your computer or phone.
   2. Open the HTTPS URL you retrieved in the previous step in your browser.
   3. Create your account and verify that you can log in successfully.
   4. Go back to the Raspberry Pi terminal, open the `.env` file, and disable future signups for security:
      ```env
      SIGNUPS_ALLOWED=false
      ```
   5. Apply the changes and recreate the containers:
      ```bash
      docker compose up -d --force-recreate
      ```

## 💾 Backup Service

The `scheduler` container runs a Python-based backup scheduler daemon that automatically creates encrypted archives of all Vaultwarden data.

### What is backed up

| File / Directory | Description                                           |
|------------------|-------------------------------------------------------|
| `db.sqlite3`     | Main Vaultwarden database (hot backup via SQLite API) |
| `config.json`    | Vaultwarden configuration (if present)                |
| `rsa_key*`       | RSA private/public keys                               |
| `attachments/`   | File attachments (if present)                         |
| `sends/`         | Send files (if present)                               |

All items are packaged into a single **password-protected, header-encrypted `.7z` archive** named `backup.YYYY-MM-DD-HHMM.7z`.

The backup scheduler daemon runs at **specific, customizable times of the day** (default: `02:00, 06:00, 10:00, 14:00, 18:00, 22:00`) and uploads the same archive to the appropriate retention tiers:

- `daily/` — on every scheduled run
- `weekly/` — additionally on the **first scheduled run** of the day on Mondays
- `monthly/` — additionally on the **first scheduled run** of the day on the first day of each month

### Storage backends

The scheduler supports two storage backends, selected automatically based on the environment configuration:

- **Local filesystem** *(default)* — archives are copied to the `./backups/` directory (mounted inside the container). Used when `S3_BUCKET` is **not** set.
- **AWS S3** — archives are uploaded directly to an S3 bucket. Activated when `S3_BUCKET` is set.
