

async function login(page, logger) {
    try {
      logger.info('Attempting to log in...');
      const response = await page.goto('https://app.brikks.co/users/sign_in');
      if (response.status() === 403) {
        logger.warn('Login page returned 403. Restarting...');
        return false;
      }
      await page.type('#user_email', process.env.EMAIL);
      await page.type('#user_password', process.env.PASSWORD);
      await Promise.all([
        page.waitForNavigation(),
        page.click('.btn-connexion')
      ]);
      logger.info('Login successful.');
      return true;
    } catch (error) {
      logger.error(`Login failed: ${error.message}`);
      return false;
    }
  }

module.exports = login;
