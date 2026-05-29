# Automated Ecommerce Bot - Admin Guide

## Admin Access
Your admin user ID is set in `config.py` / `.env` as `ADMIN_USER_ID` (get it from [@userinfobot](https://t.me/userinfobot))
Only you can access the admin panel and commands.

## Stock channel catalog

The bot can sync products, prices (from config), and availability from a **private Telegram channel**.

1. Add the bot to channel `-1002277323115` as **admin** (required for private channels).
2. Post catalog messages in the format: product title, THC/hybrid lines, description, then `❇️ Available` or `❌ Unavailable` / `❌ Unvailable`.
3. The bot updates the shop when you **post** or **edit** a channel message (with photo + caption).
4. For the first import: **forward** a catalog post from the channel to the bot in private chat.
5. `/sync_catalog` — shows how many products are in the database.

Prices per strain are set in `config.py` → `PRODUCT_PRICES` (key = slug from product name). Shop shows only **Available** items.

## Admin Panel Features

### Main Admin Panel
- **Access**: Click "Admin Panel" in the main menu (only visible to admin)
- **Features**:
  - View Orders
  - Manage Giveaways  
  - Add Discount Codes
  - Bot Statistics

### Order Management
- **View Recent Orders**: Shows last 10 orders with details
- **Export Orders**: Creates CSV file with all order data
- **Revenue Tracking**: Automatic calculation of total revenue

### Giveaway Management
- **Create Giveaways**: Use `/create_giveaway` command
- **View Active Giveaways**: See all active giveaways with entry counts
- **View Entries**: Use `/view_entries GIVEAWAY_ID` to see participants
- **Entry Tracking**: Automatic tracking of user entries and limits

### Discount Code Management
- **Add Codes**: Use `/addcode CODE PERCENT EXPIRY_DATE`
- **Example**: `/addcode SUMMER20 20 2024-08-31`

## Admin Commands

### Order Commands
```
/orders - View recent orders (10 orders)
/export_orders - Export all orders to CSV file
```

### Giveaway Commands
```
/create_giveaway TITLE DESCRIPTION PRIZE START_DATE END_DATE [MAX_ENTRIES]
/list_giveaways - View all active giveaways
/view_entries GIVEAWAY_ID - View entries for specific giveaway
```

### Discount Commands
```
/addcode CODE PERCENT YYYY-MM-DD
Example: /addcode SUMMER20 20 2024-08-31
```

### Status Commands
```
/bot_status - Get comprehensive bot status report
```

## Customer Features

### Shopping Experience
- Browse products with quantity-based pricing
- Add items to cart
- Enter shipping address
- Apply discount codes
- Complete payment via crypto payment provider

### Giveaway Participation
- View active giveaways
- Enter giveaways with one click
- Automatic entry validation
- Real-time entry tracking

### Referral System
- Generate personal referral codes
- Share codes for 10% discount
- Track referral usage

## Key Statistics Tracked

### Revenue Metrics
- Total orders
- Total revenue
- Average order value
- Revenue by time period

### Giveaway Metrics
- Active giveaways
- Total entries
- Entry per giveaway
- Popular giveaways

### User Metrics
- Unique customers
- Repeat customers
- Referral usage
- Geographic distribution

## Technical Features

### Database
- SQLite database (`orders.db`)
- Automatic table creation
- Data integrity checks
- Backup recommendations

### Security
- Admin-only access to sensitive features
- User ID validation
- Input sanitization
- Error handling

### User Interface
- Clean, intuitive menus
- Responsive button layouts
- Clear error messages
- Progress indicators

## Best Practices

### Growth Strategies
1. **Regular Giveaways**: Keep users engaged
2. **Discount Codes**: Encourage purchases
3. **Referral Rewards**: Viral growth
4. **Product Updates**: Fresh inventory

### Analytics
1. **Monitor Orders**: Track daily/weekly trends
2. **Giveaway Performance**: Analyze entry patterns
3. **Revenue Tracking**: Monitor growth
4. **User Engagement**: Track active users

### Maintenance
1. **Regular Backups**: Export data weekly
2. **Update Products**: Keep inventory fresh
3. **Monitor Performance**: Check bot status
4. **User Support**: Respond to queries

## Troubleshooting

### Common Issues
- **Bot Not Responding**: Check if running with Python 3.10
- **Database Errors**: Verify `orders.db` file exists
- **Payment Issues**: Check crypto payment provider configuration
- **Giveaway Problems**: Verify dates and limits

### Support Commands
- `/bot_status` - Check bot health
- `/orders` - Verify order system
- `/list_giveaways` - Check giveaway status

## Support
For technical support, contact: @support_handle

---
*Last Updated: July 2024* 