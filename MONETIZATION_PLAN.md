# Royale IQ Monetization Architecture

## Overview
Three-tier system: Free users → Pro subscribers → Coaching marketplace

### Tier 1: Free (No Account Needed)
- All public analytics pages
- Card stats, deck archetypes
- Counter suggestions
- Limited collection builder

### Tier 2: Pro ($4.99/month)
- All Tier 1 + Premium features:
  - Advanced analytics (hidden strategies, win predictions per-arena)
  - Unlimited deck saves
  - Custom deck notes
  - Premium coaching booking (60-min slots)
  - Ad-free experience
  - API access (for bot builders)

### Tier 3: Coaching (Variable Rate)
- Coaches: Set their own hourly rate ($20-$100/hr range)
- Platform takes 20% commission
- Coaches earn 80% of booking fees
- Monthly payouts to coaches' bank accounts (Stripe Connect)

---

## Database Schema (SQLAlchemy)

### Users Table
```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  username VARCHAR(50) UNIQUE NOT NULL,
  email VARCHAR(120) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  
  -- Pro subscription
  tier VARCHAR(20) DEFAULT 'free',  -- free | pro | coach
  subscription_start TIMESTAMP,
  subscription_end TIMESTAMP,
  stripe_customer_id VARCHAR(255),  -- Stripe customer
  
  -- Coaching info
  is_coach BOOLEAN DEFAULT FALSE,
  coach_profile_json TEXT,  -- {bio, rate_per_hour, availability, rating, verified}
  stripe_connect_id VARCHAR(255),  -- Stripe Connect account
  
  INDEX idx_email (email),
  INDEX idx_stripe_customer (stripe_customer_id)
);
```

### Subscriptions Table
```sql
CREATE TABLE subscriptions (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  stripe_subscription_id VARCHAR(255) UNIQUE,
  status VARCHAR(50),  -- active | canceled | past_due
  plan_id VARCHAR(50),  -- pro_monthly
  current_period_start TIMESTAMP,
  current_period_end TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  
  INDEX idx_user (user_id),
  INDEX idx_stripe_sub (stripe_subscription_id)
);
```

### Coaching Sessions Table
```sql
CREATE TABLE coaching_sessions (
  id INTEGER PRIMARY KEY,
  coach_id INTEGER NOT NULL REFERENCES users(id),
  student_id INTEGER NOT NULL REFERENCES users(id),
  scheduled_at TIMESTAMP NOT NULL,
  duration_minutes INTEGER,  -- 30, 60, 90
  rate_per_hour DECIMAL(8,2),
  total_fee DECIMAL(10,2),
  platform_fee DECIMAL(10,2),  -- 20% of total_fee
  coach_payout DECIMAL(10,2),  -- 80% of total_fee
  
  status VARCHAR(20) DEFAULT 'pending',  -- pending | confirmed | completed | canceled
  notes TEXT,
  meeting_link VARCHAR(500),  -- Zoom/Google Meet URL
  
  stripe_payment_intent_id VARCHAR(255),
  payment_status VARCHAR(20),  -- pending | succeeded | failed
  
  created_at TIMESTAMP DEFAULT NOW(),
  
  INDEX idx_coach (coach_id),
  INDEX idx_student (student_id),
  INDEX idx_scheduled (scheduled_at)
);
```

### Coach Payouts Table
```sql
CREATE TABLE coach_payouts (
  id INTEGER PRIMARY KEY,
  coach_id INTEGER NOT NULL REFERENCES users(id),
  payout_period_start DATE,
  payout_period_end DATE,
  total_earned DECIMAL(10,2),
  platform_fee DECIMAL(10,2),
  net_payout DECIMAL(10,2),
  
  stripe_payout_id VARCHAR(255),
  status VARCHAR(20) DEFAULT 'pending',  -- pending | completed | failed
  
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  
  INDEX idx_coach (coach_id),
  INDEX idx_stripe_payout (stripe_payout_id)
);
```

---

## Authentication Flow

### 1. Sign Up
- Email + password (bcrypt hashed)
- Redirect to onboarding
  - Free tier: Done
  - Pro tier: Stripe checkout
  - Coach tier: Profile setup + bank account linking

### 2. Login
- Email + password → JWT token (expires 7 days)
- Refresh token stored in httpOnly cookie
- Frontend stores JWT in localStorage

### 3. Session
- Every API call includes JWT
- Rate limiting by user_id (not IP)
- Pro features gated by checking `users.tier`

---

## Stripe Integration Points

### Product 1: Pro Monthly Subscription
```
Product ID: pro_monthly
Price: $4.99/month (recurring)
Checkout → Stripe Session
  ↓
Success → Create subscription row
  ↓
webhook: customer.subscription.created
  → Update users.tier = 'pro'
  → Set subscription_end = +30 days
```

### Product 2: Coaching Session Payment
```
Coach sets rate: $50/hour
Student books: 60-minute session
  ↓
Total: $50
Platform fee (20%): $10
Coach payout (80%): $40
  ↓
Stripe PaymentIntent created
  ↓
webhook: payment_intent.succeeded
  → Create coaching_sessions row
  → Send confirmation emails
  → Queue monthly payout
```

### Webhooks to Handle
- `customer.subscription.created` → Upgrade user tier
- `customer.subscription.deleted` → Downgrade to free
- `payment_intent.succeeded` → Confirm coaching session
- `charge.dispute.created` → Log dispute
- Monthly cron: Gather coach payouts, send to Stripe Connect

---

## API Endpoints

### Authentication
```
POST /api/auth/signup
  → { email, password, tier: 'free' | 'pro' | 'coach' }
  → { access_token, user: {id, email, tier} }

POST /api/auth/login
  → { email, password }
  → { access_token, user: {id, email, tier} }

POST /api/auth/refresh
  → { refresh_token }
  → { access_token }

POST /api/auth/logout
  → { }
```

### Subscriptions
```
GET /api/subscriptions/plans
  → List available plans (free, pro, coaching)

POST /api/subscriptions/checkout
  → { plan_id: 'pro_monthly' }
  → { checkout_url: 'https://checkout.stripe.com/...' }

GET /api/subscriptions/current
  → { tier, status, current_period_end, ...}

POST /api/subscriptions/cancel
  → Cancel pro subscription
```

### Coaching
```
GET /api/coaching/coaches
  → List all verified coaches (paginated, sortable by rate/rating)
  → { coaches: [{id, name, rate_per_hour, rating, bio, availability}, ...] }

GET /api/coaching/coaches/{coach_id}
  → Full coach profile + availability calendar

POST /api/coaching/sessions
  → { coach_id, scheduled_at, duration_minutes }
  → Create PaymentIntent, return checkout_url

GET /api/coaching/sessions/my-bookings (auth required)
  → List all sessions for current user (as student or coach)

POST /api/coaching/sessions/{session_id}/complete
  → Coach marks session complete, triggers payout queue

GET /api/coaching/earnings (auth required, coach only)
  → { total_earned, pending_payout, next_payout_date, sessions: [...] }

POST /api/coaching/profile (auth required, coach only)
  → { bio, rate_per_hour, expertise_tags, availability_json }
```

---

## Frontend Changes

### 1. Auth Pages
- Signup form (email, password, tier selection)
- Login form
- Verify email page
- "Upgrade to Pro" modal
- Pro checkout (Stripe.js)

### 2. User Menu
- Profile page
  - Email, password change
  - Subscription status + next billing date
  - For coaches: earnings dashboard + payout settings
- Settings page
  - Privacy, notifications
  - API keys (for pro users)

### 3. Coaching Pages (New)
- `/coaching/browse` — List of coaches, filters by rate/rating/language
- `/coaching/profile/{coach_id}` — Individual coach profile + book button
- `/coaching/my-bookings` — Student's booked sessions + history
- `/coaching/earnings` — Coach's earnings + payout info (coach only)
- `/coaching/profile/edit` — Coach profile editor (coach only)

### 4. Pro Feature Gates
- Deck saves limited to 5 on free, unlimited on pro
- Advanced analytics hidden behind pro badge
- API docs show `/api/pro-features` endpoints
- "Upgrade" CTA in feature cards

---

## Implementation Roadmap

### Week 1-2: Auth System
- [ ] Create users table + models
- [ ] Signup/login endpoints
- [ ] JWT token generation + refresh flow
- [ ] Password reset flow (email)
- [ ] React signup/login pages

### Week 3: Stripe Integration
- [ ] Create Stripe products + prices
- [ ] Implement checkout endpoints
- [ ] Setup webhook handler
- [ ] Create subscriptions table
- [ ] Tier checking middleware

### Week 4: Coaching Marketplace
- [ ] Create coaching tables (sessions, payouts)
- [ ] Coach profile endpoints
- [ ] Booking flow (calendar, checkout)
- [ ] Stripe Connect setup (for payouts)
- [ ] Coach earnings dashboard

### Week 5: Polish + Growth
- [ ] Refine UI/UX
- [ ] Email notifications (booking confirmations, payout alerts)
- [ ] Analytics on signups/conversions
- [ ] Coach recruitment flow (Fiverr/social outreach)
- [ ] Terms of service + payment policies

---

## Monetization Projections

### Conservative Estimate (Year 1)
- **Pro subscribers**: 500 @ $4.99/month = $2,495/month = **$29,940/year**
- **Coaching platform**: 50 active coaches × $300/month avg volume × 20% fee = **$36,000/year**
- **Total Revenue**: ~$66K (before payment processing fees ~2.9%)

### Growth Drivers
1. Organic SEO (meta analytics attracts deck builders)
2. Social media (TikTok: "Best Clash Royale deck builder")
3. Coach recruitment (influencers as coaches)
4. Reddit/Discord community
5. Content partnerships (YouTube channels)

---

## Security Checklist

- [ ] Passwords hashed with bcrypt (min 10 rounds)
- [ ] JWT signed with strong secret (256-bit)
- [ ] HTTPS only (force HSTS)
- [ ] CORS restricted to royaleiq.com
- [ ] Rate limiting on auth endpoints (5 attempts/min per IP)
- [ ] SQL injection prevention (SQLAlchemy ORM)
- [ ] XSS prevention (React escaping, CSP headers)
- [ ] CSRF tokens on state-changing requests
- [ ] PCI DSS compliance (Stripe handles payment data, never touch card #s)
- [ ] Regular security audits + dependency updates

---

## Next Steps

1. **Database**: Set up PostgreSQL (or SQLite locally), run migrations
2. **Auth**: Implement signup/login with bcrypt + JWT
3. **Stripe**: Create products, test checkout flow
4. **Email**: SendGrid/Mailgun for confirmations + coaching notifications
5. **Coaching**: Build coach profile + booking UI
6. **Growth**: Launch, recruit first 10 coaches, get feedback

---

**Questions to Answer Before Implementation:**

1. Do you want coaches to pre-approve their time slots (calendar) or accept requests?
2. Auto-payout to coaches monthly, or on-demand?
3. Should coach ratings be based on student reviews post-session?
4. Any geo-restrictions (US only, or worldwide)?
5. Dispute resolution policy for coaching cancellations?
6. Should pro tier include bot API access for automation?
