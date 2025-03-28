const puppeteer = require('puppeteer');
const fs = require('fs');
const winston = require('winston');
const login = require('./login');
const sendMessage = require('./send_telegram_message');
const checkForRides = require('./check_rides');

let running_after_error = false;

// Configuration du logger
const logger = winston.createLogger({
  level: 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.printf(({ timestamp, level, message }) => `[${timestamp}] ${level.toUpperCase()}: ${message}`)
  ),
  transports: [
    new winston.transports.Console(),
    new winston.transports.File({ filename: 'logs/puppeteer.log' }),
  ],
});

const SETTINGS_FILE = "settings.json";
const DEFAULT_SETTINGS = process.env.DEFAULT_SETTINGS 
    ? JSON.parse(process.env.DEFAULT_SETTINGS)
    : { monitoring: true, interval: 60, price: 300 };

// Fonction pour récupérer les paramètres de surveillance
const getSettings = () => {
  if (!fs.existsSync(SETTINGS_FILE)) {
    return DEFAULT_SETTINGS;
  }
  return JSON.parse(fs.readFileSync(SETTINGS_FILE));
};

const monitorRides = async () => {
  let browser;
  try {
    browser = await puppeteer.launch({
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
      executablePath: puppeteer.executablePath(),
      headless: process.env.HEADLESS,
      timeout: 0,
    });

    const page = await browser.newPage();
    await page.goto('https://app.brikks.co/users/sign_in');
    logger.info('Page de connexion ouverte.');

    if (!await login(page, logger)) {
      logger.error('Échec de la connexion.');
      return;
    }

    while (true) {
      const settings = getSettings();
      if (!settings.monitoring) {
        logger.info('Surveillance arrêtée via le fichier settings.json.');
        break;
      }

      logger.info('Vérification des trajets...');
      await page.reload();
      check_status = await checkForRides(page, logger);
      if (!check_status) {
        throw new Error('Échec de la vérification des trajets');
      }

      if (running_after_error) {
        logger.info('La surveillance a redémarré après une erreur et fonctionne à nouveau. ✅🚀');
        await sendMessage('✅ La surveillance a redémarré après une erreur et fonctionne à nouveau. ✅🚀');
        running_after_error = false;
      }

      logger.info(`⏳ Attente de ${settings.interval} secondes avant la prochaine vérification.`);
      await new Promise(resolve => setTimeout(resolve, settings.interval * 1000)); // Utilisation de l'intervalle défini
    }
  } catch (error) {
    logger.error(`Erreur : ${error.message}`);
    running_after_error = true;
    await sendMessage('❌ Erreur lors de la surveillance des trajets. La surveillance redémarrera automatiquement.');
  } finally {
    try {
      await browser.close();
    } catch (error) {
      logger.error(`Erreur lors de la fermeture du navigateur : ${error.message}`);
    }
  }
};

// Démarrer la surveillance en boucle
const startMonitoring = async () => {
  while (true) {
    const settings = getSettings();
    if (settings.monitoring) {
      await monitorRides();
    }
    await new Promise(resolve => setTimeout(resolve, 5000)); // Vérification du statut toutes les 5s
  }
};

startMonitoring();
