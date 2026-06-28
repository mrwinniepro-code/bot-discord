# 🚀 Mettre le bot en ligne 24h/24 (Oracle Cloud — gratuit)

Ce guide met le **bot + le dashboard** sur une machine Oracle Cloud **gratuite à vie**,
qui tourne tout le temps même PC éteint. On fait tout pas à pas.

> 💡 À chaque étape, si un message d'erreur apparaît, copie-le — on le règle ensemble.

---

## Vue d'ensemble (ce qu'on va faire)

1. Créer un compte **Oracle Cloud** (Always Free).
2. Créer une **machine Ubuntu** gratuite.
3. Ouvrir les **ports web** (80 / 443).
4. Créer une **adresse web gratuite** (DuckDNS) qui pointe sur la machine.
5. Se connecter à la machine et **installer le bot** (1 script).
6. Ajouter l'**adresse de redirection** dans Discord.
7. Vérifier que tout tourne. ✅

---

## Étape 1 — Compte Oracle Cloud

1. Va sur **https://www.oracle.com/cloud/free/** → **Start for free**.
2. Renseigne email, pays (**France**), etc.
3. **Région (IMPORTANT, définitif)** : choisis une région proche, ex. **France Central (Paris)** ou **Germany Central (Frankfurt)**.
4. Vérification d'identité par **carte bancaire** : normal, **0 € prélevé** sur l'offre Always Free.
5. Termine l'inscription → tu arrives sur la **console Oracle Cloud**.

➡️ Quand ton compte est prêt, dis-le moi, je te donne l'étape 2.

---

## Étape 2 — Créer la machine (VM Ubuntu, gratuite)

1. Menu ☰ → **Compute** → **Instances** → **Create instance**.
2. **Name** : `chadbot`.
3. **Image and shape** → **Edit** :
   - **Image** : **Canonical Ubuntu** (22.04 ou plus récent).
   - **Shape** : choisis une forme **Always Free eligible** (mention « Always Free »).
     Le plus simple/dispo : **VM.Standard.E2.1.Micro** (AMD, 1 Go).
4. **SSH keys** : choisis **Save private key** (et **Save public key**) → garde bien le fichier `.key` téléchargé : c'est ta clé pour te connecter.
5. **Create**. Attends que l'instance passe en **Running**, puis note son **Public IP address**.

➡️ Donne-moi l'adresse IP publique quand c'est fait.

---

## Étape 3 — Ouvrir les ports web (80 / 443)

Dans la page de ton instance :
1. Section **Primary VNIC** → clique sur le **Subnet**.
2. Clique sur la **Security List** par défaut → **Add Ingress Rules**.
3. Ajoute 2 règles (Source CIDR `0.0.0.0/0`, IP Protocol **TCP**) :
   - Destination Port **80**
   - Destination Port **443**
4. **Add Ingress Rules** pour valider.

*(Le port 22 / SSH est déjà ouvert par défaut.)*

---

## Étape 4 — Adresse web gratuite (DuckDNS)

Le dashboard a besoin d'une **adresse** (pour le HTTPS et la connexion Discord).

1. Va sur **https://www.duckdns.org/** → connecte-toi (Google/GitHub).
2. Choisis un sous-domaine, ex. **chadbot** → **add domain** → ça crée `chadbot.duckdns.org`.
3. Dans le champ **current ip**, mets l'**IP publique** de ta machine (étape 2) → **update ip**.

Ton adresse est maintenant : `https://chadbot.duckdns.org` (à adapter).

---

## Étape 5 — Installer le bot sur la machine

### 5a. Se connecter en SSH
Depuis ton PC Windows (PowerShell), avec la clé téléchargée à l'étape 2 :
```powershell
ssh -i "C:\chemin\vers\ta-cle.key" ubuntu@TON_IP_PUBLIQUE
```
*(Tape « yes » à la première connexion.)*

### 5b. Récupérer le projet
> Le plus simple est de mettre le projet sur **GitHub** (je t'aide à le faire), puis :
```bash
git clone https://github.com/TON_PSEUDO/bot-discord.git
cd bot-discord
```

### 5c. Créer le fichier `.env`
```bash
cp .env.example .env
nano .env
```
Remplis (comme en local) **DISCORD_TOKEN**, **DISCORD_CLIENT_ID**, **DISCORD_CLIENT_SECRET**,
et surtout :
```
DASHBOARD_BASE_URL=https://chadbot.duckdns.org
```
*(à ton adresse DuckDNS)*. Enregistre dans nano : **Ctrl+O**, **Entrée**, puis **Ctrl+X**.

### 5d. Lancer l'installation (1 commande)
```bash
bash deploy/setup.sh chadbot.duckdns.org
```
Le script installe tout, configure le HTTPS, et démarre le bot + le dashboard
**automatiquement au démarrage de la machine**.

---

## Étape 6 — Adresse de redirection Discord

Sur https://discord.com/developers/applications → ton appli → **OAuth2 → Redirects** →
**Add Redirect** :
```
https://chadbot.duckdns.org/callback
```
**Save Changes**.

---

## Étape 7 — Vérifier ✅

- Le **bot** apparaît **en ligne** sur Discord (et le reste, PC éteint).
- Le **dashboard** est accessible sur `https://chadbot.duckdns.org`.

### Commandes utiles sur le serveur
```bash
# Voir l'état / les logs
sudo systemctl status chadbot
sudo journalctl -u chadbot -f             # logs du bot en direct
sudo journalctl -u chadbot-dashboard -f   # logs du dashboard

# Redémarrer
sudo systemctl restart chadbot chadbot-dashboard
```

### Mettre à jour le bot plus tard
```bash
cd ~/bot-discord && bash deploy/update.sh
```

---

🎉 **C'est en ligne 24h/24, gratuitement !**
