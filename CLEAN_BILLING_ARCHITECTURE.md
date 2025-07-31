# Mozaiks Platform Billing Architecture

This document outlines the two-level billing system that powers the Mozaiks platform and how token usage flows through the system.

## Overview

Mozaiks operates a **two-level billing system** where we act as the middleware provider between app creators and their end users, taking a percentage of all transactions while providing the infrastructure and token management.

## Entity Definitions

### Core Identifiers

- **`enterprise_id`**: Unique App Identifier - identifies a specific app created by a Mozaiks user
- **`user_id`**: Mozaiks Platform Customer - the person/company who uses Mozaiks to create apps
- **`platform_user_id`**: App End User - the customers of the Mozaiks user's app

### Database Architecture

- **Platform Database**: Tracks Mozaiks users and their apps (`user_id` + `enterprise_id`)
- **App Databases**: Individual databases per app (`enterprise_id`) tracking only app end users (`platform_user_id`)

## Two-Level Billing Flow

```
┌─────────────────┐    Level 1 Billing    ┌──────────────────┐
│   Mozaiks       │◄───────────────────────│   Mozaiks User   │
│   Platform      │   (App Creation Tokens) │   (Our Customer) │
└─────────────────┘                        └──────────────────┘
                                                      │
                                                      │ Level 2 Billing
                                                      │ (App Usage Tokens)
                                                      ▼
                                           ┌──────────────────┐
                                           │   App End Users  │
                                           │ (Their Customers)│
                                           └──────────────────┘
```

### Level 1: Mozaiks → Mozaiks User (App Creation)

**What**: Tokens used to BUILD and GENERATE apps
**Who Pays**: `user_id` (Mozaiks customer)
**Who Bills**: Mozaiks Platform
**Token Usage**:
- Generator workflows (creating app architecture)
- Concept creation workflows  
- App modification and updates
- Development assistance tools

**Billing Method**: Direct Mozaiks subscription/token packages

### Level 2: Mozaiks User → App End Users (App Usage)

**What**: Tokens used by end users USING the deployed app
**Who Pays**: `platform_user_id` (app end users)
**Who Bills**: Mozaiks User (via MozaiksStream)
**Token Usage**:
- Agentic workflows within the deployed app
- Chat interactions with app agents
- AI-powered features in the app

**Billing Method**: MozaiksStream + Stripe integration
- Subscription models with token packages
- **Mozaiks takes a percentage** of all transactions
- Automated billing through Stripe

## MozaiksStream Role

MozaiksStream is the **billing infrastructure** that enables Mozaiks users to monetize their apps:

### Features
- **Stripe Integration**: Automated subscription and payment processing
- **Token Package Management**: Flexible pricing tiers for end users
- **Revenue Sharing**: Automatic percentage collection for Mozaiks
- **Analytics Dashboard**: Usage tracking and billing insights
- **White-label**: Appears as the Mozaiks user's billing system

### Revenue Model
- Mozaiks takes a **percentage** of all app subscriptions
- App creators set their own pricing
- End users pay the app creator
- Mozaiks automatically collects platform fee

## Self-Hosting Option

### Architecture
- Customer pays Mozaiks for self-hosting license
- App runs on customer's infrastructure
- **Token tracking still flows through Mozaiks** for analytics
- Dashboard access through Mozaiks platform

### Billing Flow
- Customer pays Mozaiks for hosting rights
- Customer directly bills their end users
- Mozaiks tracks tokens for analytics only
- No percentage sharing (flat hosting fee instead)

## Token Tracking Requirements

### Real-Time Analytics Integration
All token tracking includes comprehensive analytics capabilities:
- **Performance monitoring** with agent response time tracking
- **Cost intelligence** with real-time threshold monitoring  
- **Session aggregation** for workflow optimization insights
- **Historical comparison** against workflow averages

### Platform Level Tracking (Level 1)
```json
{
  "level": "platform",
  "user_id": "user_123",
  "enterprise_id": "app_456", 
  "workflow_type": "app_generation",
  "tokens_used": 15000,
  "cost": 0.45,
  "billing_target": "mozaiks_user"
}
```

### App Level Tracking (Level 2)
```json
{
  "level": "app_usage",
  "enterprise_id": "app_456",
  "user_id": "user_123",      // NEEDED: For revenue sharing & analytics
  "platform_user_id": "enduser_789",
  "workflow_type": "chat_interaction", 
  "tokens_used": 500,
  "cost": 0.015,
}
```

## Implementation Architecture

### Token Manager Responsibilities
1. **Dual-level tracking**: Platform creation vs app usage
2. **Cost calculation**: Different pricing for each level
3. **Usage validation**: Trial limits, balance checking
4. **Billing preparation**: Data formatted for Stripe/internal billing
5. **Real-time analytics**: Performance monitoring and cost intelligence

### Persistence Manager Responsibilities  
1. **Platform persistence**: `user_id` billing data
2. **App persistence**: `platform_user_id` usage data per app
3. **Analytics aggregation**: Cross-app insights for dashboards
4. **Audit trails**: Complete billing transparency
5. **Performance tracking**: Session-level analytics with workflow comparison

### MozaiksStream Integration
1. **Stripe webhook handling**: Payment processing
2. **Subscription management**: Token package renewals
3. **Revenue sharing**: Automatic Mozaiks fee collection
4. **Real-time limits**: Block usage when balance exhausted

## Business Implications

### For Mozaiks
- **Recurring revenue** from platform subscriptions (Level 1)
- **Percentage-based revenue** from all app transactions (Level 2)
- **Hosting revenue** from self-hosted customers
- **Network effects** as more apps = more transactions

### For Mozaiks Users
- **Low barrier to entry**: Create apps without upfront costs
- **Built-in monetization**: MozaiksStream handles all billing complexity
- **Scalable pricing**: Token-based model grows with usage
- **Analytics insights**: Understand customer usage patterns

### For App End Users
- **Transparent pricing**: Pay only for what they use
- **Familiar billing**: Standard subscription models
- **Multiple payment options**: Via Stripe integration
- **Usage visibility**: Clear token consumption tracking

## Security & Compliance

### Data Isolation
- Each app gets its own database (`enterprise_id`)
- Platform data separate from app data
- End user data never mixed between apps

### Billing Security
- All payments processed through Stripe
- Revenue sharing calculated server-side
- Audit logs for all billing events
- Compliance with PCI DSS standards

### Privacy
- App end users' data stays in app databases
- Mozaiks only sees aggregated analytics
- Self-hosted option for sensitive use cases

## Future Considerations

### Scaling
- Multi-region deployments for app databases
- Automated billing reconciliation
- Advanced analytics and ML insights
- Enterprise features (custom contracts, volume discounts)

### Product Evolution
- Multiple pricing models (fixed, usage-based, hybrid)
- Marketplace for pre-built app templates
- Revenue optimization tools for app creators
- Advanced self-hosting options (on-premise, private cloud)
