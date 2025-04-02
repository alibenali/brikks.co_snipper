const fs = require('fs');
const login = require('./login.js');
const sendMessage = require('./send_telegram_message.js');

const SETTINGS_FILE = 'settings.json';
const DEFAULT_SETTINGS = process.env.DEFAULT_SETTINGS 
    ? JSON.parse(process.env.DEFAULT_SETTINGS)
    : { monitoring: true, interval: 60, price: 300 };

// Fonction pour récupérer les paramètres
const getSettings = () => {
    if (!fs.existsSync(SETTINGS_FILE)) {
        return DEFAULT_SETTINGS;
    }
    return JSON.parse(fs.readFileSync(SETTINGS_FILE));
};

async function checkForRides(page, logger) {
    try {
        const settings = getSettings();
        const minPrice = settings.price || DEFAULT_SETTINGS.price;

        logger.info('Vérification des trajets disponibles...');
        const response = await page.goto('https://app.brikks.co/d/rides');
        if (response.status() === 403) {
            throw new Error('La page des trajets a renvoyé 403. Redémarrage...');
            return flase;
        }

        const loginForm = await page.$('form.simple_form');
        if (loginForm) {
            logger.info('Formulaire de connexion détecté. Nouvelle tentative de connexion...');
            if (!await login(page, logger)) {
                throw new Error('Échec de la connexion.');
            }
        }

        const rides = await page.evaluate((minPrice) => {
            const availableRides = [];
            const panels = document.querySelectorAll('.panel-default');
            panels.forEach(panel => {
                const priceText = panel.querySelector('.label-price')?.textContent || '';
                const price = parseFloat(priceText.replace('€', '').replace(',', '.'));
                if (price >= minPrice) {
                    availableRides.push({
                        price,
                        route: panel.querySelector('.col-md-7')?.textContent?.trim(),
                        departure: panel.querySelector('.col-md-1 .row:first-child')?.textContent?.trim(),
                        departureTime: panel.querySelector('.col-md-1 .text-muted')?.textContent?.trim(),
                        acceptUrl: panel.querySelector('.panel-cta a')?.getAttribute('href')
                    });
                }
            });
            return availableRides;
        }, minPrice);

        logger.info(`Nombre de trajets trouvés répondant aux critères (min ${minPrice}€) : ${rides.length}`);
        for (const ride of rides) {
            logger.info(`Traitement du trajet : ${JSON.stringify(ride)}`);
            if (ride.acceptUrl) {
                await sendMessage(
                    chat_id=process.env.CHAT_ID,
                    message=`💰 Trajet trouvé : ${ride.price}€\n🛣️ Itinéraire : ${ride.route}\n🕒 Départ : ${ride.departure} à ${ride.departureTime}`
                );

                try {
                    await page.click(`.panel-cta a[href="${ride.acceptUrl}"]`);
                    await page.waitForNavigation({ timeout: 5000 });
                    await sendMessage(chat_id=process.env.CHAT_ID,message='✅ Trajet accepté avec succès !');
                    logger.info('Trajet accepté avec succès.');
                } catch (error) {
                    await sendMessage(chat_id=process.env.CHAT_ID, message='❌ Échec de l’acceptation du trajet');
                    logger.error(`Échec de l’acceptation du trajet : ${error.message}`);
                }
            }
        }
        return true;
    } catch (error) {
        logger.error(`Erreur lors de la vérification des trajets : ${error.message}`);
        return false;
    }
}

module.exports = checkForRides;