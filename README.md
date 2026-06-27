# Bot Discord multifonction (type DraftBot, gratuit)

Un bot Discord tout-en-un, **gratuit**, configurable, avec à terme un **dashboard web**.
Construit en **Python** (`discord.py` + `Pillow`).

## ✅ Déjà disponible (Phase 0 + 1)

- **Arrivées / départs** : messages personnalisables + **carte de bienvenue en image**.
- **Auto-rôles** : rôle(s) donné(s) automatiquement à chaque arrivée.
- **Panneaux de rôles à boutons** : les membres cliquent pour prendre/retirer un rôle.
- `/ping`, `/aide`.

## 🛣️ À venir

Modération + logs · tickets · giveaways · sondages · niveaux (XP) · économie · **dashboard web** · hébergement 24h/24.

---

## 🚀 Installation (sur ton PC, pour tester)

### 1. Installer les dépendances

```powershell
python -m pip install -r requirements.txt
```

### 2. Créer le bot sur Discord

1. Va sur **https://discord.com/developers/applications** → **New Application** (donne un nom).
2. Menu **Bot** → **Reset Token** → **Copy** (c'est ton `DISCORD_TOKEN`, garde-le secret !).
3. Toujours dans **Bot**, active les deux interrupteurs :
   - ✅ **SERVER MEMBERS INTENT**
   - ✅ **MESSAGE CONTENT INTENT**
4. Menu **OAuth2 → URL Generator** :
   - Scopes : coche **`bot`** et **`applications.commands`**
   - Bot Permissions : coche au minimum **Manage Roles**, **Manage Channels**,
     **Kick Members**, **Ban Members**, **Manage Messages**, **Send Messages**,
     **Embed Links**, **Attach Files**, **Read Message History**.
   - Copie l'URL générée en bas, ouvre-la, et **invite le bot sur ton serveur**.

### 3. Configurer le token

```powershell
copy .env.example .env
```

Ouvre `.env` et colle ton token dans `DISCORD_TOKEN=`.
Mets aussi l'**ID de ton serveur** dans `DEV_GUILD_ID=` (clic droit sur ton serveur →
« Copier l'identifiant », après avoir activé le **Mode développeur** dans Discord →
Paramètres → Avancés). Ça fait apparaître les commandes **instantanément**.

### 4. Lancer le bot

```powershell
python run_bot.py
```

Le bot doit passer **en ligne**. Teste `/ping` dans ton serveur.

---

## ⚙️ Configurer les modules

Toutes les commandes de config sont réservées aux membres ayant **Gérer le serveur**.

| Commande | Effet |
|---|---|
| `/bienvenue salon #salon` | Définit le salon d'arrivée (active le module) |
| `/bienvenue message <texte>` | Texte du message d'arrivée |
| `/bienvenue titre <texte>` | Texte affiché sur la carte image |
| `/bienvenue carte <true/false>` | Affiche/masque la carte image |
| `/bienvenue apercu` | Aperçu immédiat |
| `/aurevoir salon #salon` | Salon de départ |
| `/aurevoir message <texte>` | Texte du message de départ |
| `/autorole ajouter @role` | Rôle donné à l'arrivée |
| `/panneaurole creer #salon "Titre"` | Crée un panneau de rôles |
| `/panneaurole ajouter id:1 role:@role` | Ajoute un bouton de rôle |

**Variables de message** : `{user_mention}`, `{user_name}`, `{user}`, `{server}`, `{count}`.

---

## 📁 Structure

```
bot/
  main.py        # démarrage du bot
  config.py      # lecture du .env
  database.py    # base de données (SQLAlchemy + SQLite)
  cogs/          # modules : general, welcome, autoroles...
  utils/         # images (carte Pillow), permissions
data/            # base SQLite + polices/fonds (auto-créé)
```
