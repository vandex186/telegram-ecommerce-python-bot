# Automated Ecommerce Bot - Telegram

A comprehensive Telegram bot for managing an automated ecommerce shop with advanced features including order management, giveaways, discount codes, and payment processing.

**Repository:** [github.com/wrogg/telegram-ecommerce-python-bot](https://github.com/wrogg/telegram-ecommerce-python-bot)

## Catalog variants (branches)

This project has two catalog modes on separate branches:

| Branch | Mode |
|--------|------|
| [`catalog/inline-buttons`](BRANCHES.md) | Products as inline menu buttons (`config.PRODUCTS`) |
| [`catalog/channel-cards`](BRANCHES.md) | Product cards synced from a private Telegram channel |

See **[BRANCHES.md](BRANCHES.md)** for descriptions and how to fork/switch branches.

## Run 24/7

GitHub stores the code only. For a bot that runs around the clock, deploy to Render, Railway, or a VPS — see **[DEPLOY.md](DEPLOY.md)**.

## Features

### Shopping System
- **Product Catalog**: Browse products with quantity-based pricing
- **Shopping Cart**: Add items and manage quantities
- **Address Collection**: Secure shipping address input
- **Discount Codes**: Apply promotional codes for savings
- **Payment Processing**: Integrated crypto payment provider such as Oxapay

### Giveaway System
- **Create Giveaways**: Admin can create promotional giveaways
- **User Participation**: One-click entry system
- **Entry Tracking**: Automatic validation and limits
- **Winner Selection**: Random winner selection with transparency

### Discount & Referral System
- **Discount Codes**: Admin-managed promotional codes
- **Referral System**: User-generated referral codes with 10% discount
- **Code Validation**: Automatic expiration and usage tracking

### Admin Panel
- **Order Management**: View and export order data
- **Revenue Tracking**: Comprehensive sales analytics
- **Giveaway Management**: Create and monitor giveaways
- **User Analytics**: Customer behavior insights
- **Broadcast Messages**: Send announcements to all users

### Security Features
- **Admin Authentication**: User ID-based admin access
- **Input Validation**: Sanitized user inputs
- **Database Security**: SQL injection prevention
- **Error Handling**: Comprehensive error management

## Technical Stack

- **Language**: Python 3.10+
- **Framework**: python-telegram-bot 20+
- **Database**: SQLite with automatic schema creation
- **Payment**: Crypto payment provider API integration
- **Architecture**: Event-driven with async/await

## Installation

### Prerequisites
- Python 3.10 or higher
- Telegram Bot Token (from @BotFather)
- Crypto Payment Provider API Key (optional, for payment processing)

### Setup Instructions

1. **Clone the repository** (pick a branch — see [BRANCHES.md](BRANCHES.md))
   ```bash
   git clone https://github.com/wrogg/telegram-ecommerce-python-bot.git
   cd telegram-ecommerce-python-bot
   git checkout catalog/channel-cards   # or catalog/inline-buttons
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the bot**
   - Copy `config.example.py` to `config.py`
   - Update `config.py` with your settings:
     ```python
     TELEGRAM_BOT_TOKEN = "your_bot_token_here"
     OXAPAY_API_KEY = "your_crypto_payment_api_key"  # Optional
     ADMIN_USER_ID = 123456789  # Your Telegram user ID
     ```

4. **Customize products**
   - Edit the `PRODUCTS` list in `config.py`
   - Add your product images to the project directory
   - Update product details, prices, and descriptions

5. **Run the bot**
   ```bash
   ./run.sh
   ```
   Or see [DEPLOY.md](DEPLOY.md) for 24/7 hosting.

## Configuration

### Environment Variables
- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token
- `OXAPAY_API_KEY`: Crypto payment provider API key for payments
- `ADMIN_USER_ID`: Your Telegram user ID for admin access

### Product Configuration
```python
PRODUCTS = [
    {
        "id": 1,
        "name": "Product Name",
        "description": "Product description",
        "prices": {1: 10.0, 5: 45.0, 10: 80.0},  # Quantity: Price
        "image": "product_image.jpg"
    }
]
```

## Database Schema

### Orders Table
- `id`: Primary key
- `timestamp`: Order timestamp
- `user_id`: Customer Telegram ID
- `product_id`: Product identifier
- `product_name`: Product name
- `quantity`: Order quantity
- `price`: Total price
- `invoice_id`: Payment invoice ID
- `discount_code`: Applied discount code
- `discount_percent`: Discount percentage
- `referred_by`: Referral code used
- `address`: Shipping address

### Discount Codes Table
- `code`: Discount code
- `percent`: Discount percentage
- `expires`: Expiration date

### Giveaways Table
- `id`: Giveaway ID
- `title`: Giveaway title
- `description`: Giveaway description
- `prize`: Prize description
- `start_date`: Start date
- `end_date`: End date
- `max_entries`: Maximum entries allowed
- `is_active`: Active status

## Admin Commands

### Order Management
- `/orders` - View recent orders
- `/export_orders` - Export orders to CSV

### Giveaway Management
- `/create_giveaway TITLE DESCRIPTION PRIZE START_DATE END_DATE [MAX_ENTRIES]`
- `/list_giveaways` - View active giveaways
- `/view_entries GIVEAWAY_ID` - View giveaway entries

### Discount Management
- `/addcode CODE PERCENT YYYY-MM-DD` - Add discount code

### System Status
- `/bot_status` - Get comprehensive bot status

## User Features

### Shopping Experience
1. Start the bot with `/start`
2. Browse products from the main menu
3. Select product and quantity
4. Add to cart
5. Enter shipping address
6. Apply discount codes (optional)
7. Complete payment via crypto payment provider

### Giveaway Participation
1. View active giveaways
2. Click "Enter Giveaway" button
3. Automatic entry validation
4. Real-time entry tracking

### Referral System
1. Generate personal referral code
2. Share code with others
3. Both parties receive 10% discount

## Security Considerations

### Data Protection
- All user data is stored locally in SQLite database
- No sensitive data is transmitted to third parties
- Admin access is restricted to specific user IDs

### Payment Security
- Crypto payment provider handles all payment processing
- No payment data is stored locally
- Secure API communication with payment provider

### Input Validation
- All user inputs are sanitized
- SQL injection prevention
- Rate limiting on admin commands

## Deployment

### Local Development
```bash
python bot.py
```

### Production Deployment
1. Use a VPS or cloud service
2. Set up process manager (PM2, Supervisor)
3. Configure SSL certificates
4. Set up automated backups
5. Monitor bot performance

### Docker Deployment
```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For technical support or questions:
- Create an issue on GitHub
- Contact: [Your Contact Information]

## Disclaimer

This bot is for educational and demonstration purposes. Ensure compliance with local regulations regarding ecommerce operations and payment processing.

---

**Built with clean code and modern design principles** 