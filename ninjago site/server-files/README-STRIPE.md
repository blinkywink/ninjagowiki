# Stripe Checkout Setup

## Installation

1. Install the Stripe Python library:
```bash
pip3 install stripe
```

Or install from requirements.txt:
```bash
pip3 install -r server-files/requirements.txt
```

## Configuration

**IMPORTANT:** You need your Stripe **SECRET KEY** (not the publishable key you provided).

1. Get your secret key from: https://dashboard.stripe.com/apikeys
   - It starts with `sk_live_` (live mode) or `sk_test_` (test mode)
   - For testing, use test mode keys

2. Set it as an environment variable before starting the server:

**On Mac/Linux:**
```bash
export STRIPE_SECRET_KEY=sk_live_your_secret_key_here
```

**On Windows:**
```cmd
set STRIPE_SECRET_KEY=sk_live_your_secret_key_here
```

**Or set it in the terminal where you start the server:**
```bash
STRIPE_SECRET_KEY=sk_live_your_key_here python3 server-files/server.py
```

## Testing

1. Make sure Stripe is installed: `pip3 install stripe`
2. Set your STRIPE_SECRET_KEY environment variable
3. Start the server using `Start Server.command` or `python3 server-files/server.py`
4. Add items to cart
5. Click "Checkout" button
6. You'll be redirected to Stripe Checkout

## Troubleshooting

- **"Stripe library not installed"**: Run `pip3 install stripe`
- **"Stripe secret key not configured"**: Set the STRIPE_SECRET_KEY environment variable
- **Check server console**: The server will print detailed error messages
- **Check browser console**: Open DevTools (F12) to see JavaScript errors

## Notes

- You provided a publishable key (`pk_live_...`), but the server needs the **secret key** (`sk_live_...`)
- For testing, use test mode keys (sk_test_ and pk_test_)
- The publishable key is not needed for server-side checkout

