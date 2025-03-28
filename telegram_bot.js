const TelegramBot = require("node-telegram-bot-api");
const fs = require("fs");
const winston = require("winston");
require("dotenv").config();

// Configuration du logger
const logger = winston.createLogger({
  level: "info",
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.printf(
      ({ timestamp, level, message }) =>
        `[${timestamp}] ${level.toUpperCase()}: ${message}`
    )
  ),
  transports: [
    new winston.transports.Console(),
    new winston.transports.File({ filename: "logs/bot.log" }),
  ],
});

// Configuration du bot Telegram
const bot = new TelegramBot(process.env.TELEGRAM_BOT_TOKEN, {
  polling: true,
});

const SETTINGS_FILE = "settings.json";

// Paramètres par défaut
const DEFAULT_SETTINGS = {
  monitoring: false,
  interval: 60, // Intervalle par défaut en secondes
  price: 300, // Seuil de prix minimum en euros
};

// Fonction pour lire les paramètres
const getSettings = () => {
  if (!fs.existsSync(SETTINGS_FILE)) {
    return DEFAULT_SETTINGS;
  }
  return JSON.parse(fs.readFileSync(SETTINGS_FILE));
};

// Fonction pour mettre à jour les paramètres
const updateSettings = (newSettings) => {
  const settings = { ...getSettings(), ...newSettings };
  fs.writeFileSync(SETTINGS_FILE, JSON.stringify(settings, null, 2));
  logger.info(`Paramètres mis à jour : ${JSON.stringify(newSettings)}`);
};

// Commande /start
bot.onText(/\/start/, (msg) => {
  const chatId = msg.chat.id;
  const settings = getSettings();

  if (settings.monitoring) {
    bot.sendMessage(chatId, "🔄 La surveillance est déjà active.");
  } else {
    updateSettings({ monitoring: true });
    bot.sendMessage(
      chatId,
      `🟢 Surveillance démarrée.\n⏳ Intervalle : ${settings.interval}s\n💰 Seuil de prix : ${settings.price}€`
    );
  }
});

// Commande /stop
bot.onText(/\/stop/, (msg) => {
  const chatId = msg.chat.id;
  const settings = getSettings();

  if (!settings.monitoring) {
    bot.sendMessage(chatId, "⏸ La surveillance est déjà arrêtée.");
  } else {
    updateSettings({ monitoring: false });
    bot.sendMessage(chatId, "🔴 Surveillance arrêtée.");
  }
});

// Commande /status
bot.onText(/\/status/, (msg) => {
  const chatId = msg.chat.id;
  const settings = getSettings();
  const status = settings.monitoring
    ? "🟢 Surveillance active"
    : "🔴 Surveillance arrêtée";

  bot.sendMessage(
    chatId,
    `${status}\n⏳ Intervalle : ${settings.interval}s\n💰 Seuil de prix : ${settings.price}€`
  );
});

// Commande pour modifier l’intervalle
bot.onText(/\/set_interval/, (msg) => {
  const chatId = msg.chat.id;
  bot.sendMessage(
    chatId,
    "⏳ Envoyez un nombre pour définir l'intervalle (ex: 60 secondes) :",
    {
      parse_mode: "HTML",
      reply_markup: { force_reply: true },
    }
  );
});

// Gestion des réponses de l'utilisateur pour l'intervalle
bot.on("message", (msg) => {
  logger.info(`Message reçu : ${JSON.stringify(msg)}`);
  if (msg.reply_to_message && msg.reply_to_message.text.includes("intervalle")) {
    const chatId = msg.chat.id;
    const newInterval = parseInt(msg.text, 10);

    if (isNaN(newInterval) || newInterval < 2) {
      bot.sendMessage(
        chatId,
        "⚠️ L'intervalle doit être un nombre valide d'au moins 2 secondes."
      );
      return;
    }

    updateSettings({ interval: newInterval });
    bot.sendMessage(
      chatId,
      `⏳ Intervalle de surveillance mis à jour à ${newInterval} secondes.`
    );
  }
});

// Commande pour modifier le seuil de prix
bot.onText(/\/set_price/, (msg) => {
  const chatId = msg.chat.id;
  bot.sendMessage(
    chatId,
    "💰 Envoyez un montant pour définir le seuil de prix (ex: 300 euros) :",
    {
      parse_mode: "HTML",
      reply_markup: { force_reply: true },
    }
  );
});

// Gestion des réponses de l'utilisateur pour le prix
bot.on("message", (msg) => {
  if (msg.reply_to_message && msg.reply_to_message.text.includes("seuil de prix")) {
    const chatId = msg.chat.id;
    const newPrice = parseFloat(msg.text);

    if (isNaN(newPrice) || newPrice < 50 || newPrice > 1000) {
      bot.sendMessage(
        chatId,
        "⚠️ Le seuil de prix doit être un nombre entre 50 et 1000 euros."
      );
      return;
    }

    updateSettings({ price: newPrice });
    bot.sendMessage(chatId, `💰 Seuil de prix mis à jour à ${newPrice}€.`);
  }
});

// Commande pour aide à l’utilisateur
bot.onText(/\/help/, (msg) => {
  const chatId = msg.chat.id;
  bot.sendMessage(
    chatId,
    `*🔄 Commandes disponibles :*\n
/start \\- Démarrer la surveillance\n
/stop \\- Arrêter la surveillance\n
/status \\- Afficher l’état de la surveillance\n
/set\\_interval \\- Modifier l’intervalle de surveillance\n
/set\\_price \\- Modifier le seuil de prix\n`,
    { parse_mode: "MarkdownV2" }
  );
});
