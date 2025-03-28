require('dotenv').config();

async function sendMessage(chat_id=process.env.CHAT_ID, message) {
    try {
        const response = await fetch(`https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                chat_id: chat_id,
                text: message
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Telegram API error: ${errorText}`);
        }

        return await response.json();
    } catch (error) {
        console.error(`Error sending message: ${error.message}`);
    }
}

module.exports = sendMessage;
