# Used Car Finder MVP — Product Requirements Document (PRD)
Version: 1.0
Status: MVP
Platform: Responsive Web Application

## Addendum: Audience Refinement (2026-07-18)
The sections below have been lightly revised to sharpen the target audience from "people shopping for a used vehicle" to "Bay Area buyers specifically hunting for good deals." This changes what "core value" means for the MVP: speed-to-notification and price/value signals matter more than search breadth or filter completeness. See `research/mvp-checklist.md` for how this reprioritizes the build order.

Non-Goals (2.5) and Future Roadmap (8) are intentionally left mostly as originally scoped — pulling a minimal deal signal forward into MVP is flagged there as an open decision, not resolved here.

## 1. Introduction

### 1.1 Overview
Used Car Finder is a web application that helps Bay Area buyers find good deals on used vehicles across multiple online marketplaces through a single search experience. Instead of manually searching Facebook Marketplace, Craigslist, Cars.com, Autotrader, and dealership websites individually — and refreshing each one repeatedly hoping to catch an underpriced listing before someone else does — users can search once and view aggregated results from every supported source.

The application is not a marketplace. It does not facilitate messaging, payments, financing, or vehicle purchases. Its purpose is to discover listings, organize them into a consistent format, and notify users as soon as vehicles matching their preferences become available.

The initial release focuses exclusively on the San Francisco Bay Area and is designed to validate one core hypothesis: buyers are willing to rely on a dedicated search platform if it consistently surfaces good-value vehicles faster than manually searching multiple websites.

### 1.2 Problem Statement
The used car buying process is fragmented across numerous websites, each containing only a subset of available inventory. Buyers often spend weeks repeatedly refreshing multiple marketplaces throughout the day in hopes of finding a vehicle before someone else purchases it.

Because there is no centralized discovery platform, valuable listings are frequently missed simply because they were posted on a marketplace the buyer was not actively monitoring.

The current process rewards persistence rather than efficiency.

### 1.3 Vision
The long-term vision is to become the fastest and most intelligent used vehicle discovery platform.

Rather than competing with existing marketplaces, Used Car Finder becomes the intelligence layer above them. Users define exactly what they are looking for once, and the application continuously searches on their behalf, notifying them immediately whenever a matching listing appears.

### 1.4 Goals
The primary objective of the MVP is to eliminate the need for buyers to manually search multiple websites.

A successful MVP allows users to define a search once, save it, and trust the application to continuously monitor every supported marketplace for matching vehicles.

## 2. Product Scope

### 2.1 Target Audience
The initial audience consists of Bay Area buyers actively looking for a good deal on a used vehicle, not just any listing that happens to match a make and model. This includes first-time buyers, students, commuters, families, automotive enthusiasts, and electric vehicle shoppers — united by being price-sensitive and willing to act fast when a strong deal appears.

### 2.2 Geographic Scope
The MVP is limited to listings located within the San Francisco Bay Area, including San Francisco, Oakland, Berkeley, Fremont, Palo Alto, Mountain View, Sunnyvale, San Jose, Redwood City, San Mateo, Santa Clara, and surrounding communities.

The architecture should support expansion into additional metropolitan areas without requiring significant changes.

### 2.3 Platform
The MVP will launch as a responsive web application optimized for desktop and mobile browsers.

Building for the web enables rapid iteration, eliminates installation friction, and allows users to access the application from any device. Native mobile applications may be developed in the future using the same backend APIs.

### 2.4 Data Sources
Vehicle listings are aggregated from supported third-party marketplaces and normalized into a consistent internal format.

The frontend should treat every listing identically regardless of its source while still displaying the originating marketplace for transparency.

### 2.5 Non-Goals
The MVP intentionally excludes AI-generated summaries, deal scoring, VIN decoding, ownership cost estimation, financing tools, dealer ratings, image analysis, and market analytics. These features provide additional value but are not required to validate the core product.

Given the refined deal-hunter audience above, deal scoring specifically is worth revisiting for a minimal version rather than a hard exclusion — a crude "$X below similar listings" signal, not the full roadmap item — see the open decision in `research/mvp-checklist.md`. The remaining items stay out of scope for MVP.

## 3. User Experience

### 3.1 User Journey
The application is designed around a simple workflow.

A user visits the website, searches for a vehicle, applies filters, and browses matching listings from multiple marketplaces. When an interesting vehicle is found, the user can either save it to their favorites or save the search itself for continuous monitoring.

Once a search has been saved, the backend continuously watches incoming listings and alerts the user whenever a new matching vehicle appears.

The application ultimately redirects users to the original marketplace listing where communication with the seller occurs.

### 3.2 Navigation
The application should maintain a clean and minimal navigation structure.

Primary sections include:
- Search
- Saved Searches
- Favorites
- Profile

Navigation should remain consistent across desktop and mobile layouts.

### 3.3 Search Experience
Search is the primary interaction within the application.

Users begin by entering a make and model. As they type, autocomplete suggestions help complete vehicle names quickly. After selecting a vehicle, users refine their search using practical filters including maximum price, minimum model year, maximum mileage, transmission, seller type, and search radius.

Search results should update quickly without requiring page refreshes.

### 3.4 Listing Experience
Search results are presented as clean listing cards containing the primary vehicle image, asking price, year, make, model, mileage, location, marketplace source, and posting time.

Selecting a listing opens a detailed page containing all available information collected from the source marketplace, including additional images, seller description, specifications, and a prominent button that redirects users to the original listing.

### 3.5 Saved Searches
Saved Searches represent the application's primary retention feature.

Users may save any search configuration, including every applied filter. The application stores these searches and continuously evaluates newly indexed listings against them.

Saved searches should remain synchronized across devices through the user's account.

### 3.6 Notifications
Whenever a newly indexed listing satisfies one of a user's saved searches, the application should immediately notify the user.

The web application supports browser notifications for users who grant permission and email notifications as a fallback.

Notification delivery should prioritize speed over batching.

### 3.7 Favorites
Users may bookmark interesting vehicles while browsing.

Favorites act as a lightweight watchlist, allowing users to revisit listings without performing another search.

## 4. Functional Requirements

### 4.1 Search
The application must allow users to search by vehicle make and model.

Autocomplete should suggest valid manufacturers and models while typing.

Search results should return in under one second under normal operating conditions.

### 4.2 Filters
Users must be able to refine searches using:
- Maximum price
- Minimum model year
- Maximum mileage
- Search radius
- Seller type
- Transmission

Additional filters may be introduced after MVP validation.

### 4.3 Sorting
Results should support sorting by:
- Newest Listings
- Lowest Price
- Highest Price
- Lowest Mileage

Newest Listings is the default sort order.

For the refined deal-hunter audience, Lowest Price is arguably a stronger default than Newest Listings — flagged for reconsideration rather than changed unilaterally here.

### 4.4 Listings
Every listing should contain a standardized set of information regardless of its source, including pricing, mileage, location, photos, description, posting time, and marketplace attribution.

Clicking Open Original Listing should redirect users to the marketplace in a new browser tab.

### 4.5 Saved Searches
Users can create, edit, rename, enable, disable, and delete saved searches.

Each saved search should be evaluated automatically whenever new listings are indexed.

### 4.6 Notifications
Notifications are generated only for newly indexed listings that satisfy active saved searches.

Duplicate notifications should never be sent for the same listing.

### 4.7 Favorites
Users can add or remove listings from Favorites at any time.

Favorite status should remain synchronized with the user's account.

## 5. Technical Architecture

### 5.1 Frontend
The frontend is implemented as a responsive single-page web application.

Its responsibilities include rendering the interface, managing user authentication, displaying search results, handling filtering, managing saved searches and favorites, and receiving browser notifications.

### 5.2 Backend
The backend continuously ingests vehicle listings from supported marketplaces, normalizes listing data, stores records in the database, exposes search APIs, evaluates saved searches, and generates notifications.

Business logic remains exclusively on the server.

### 5.3 Database
The primary entities include Users, Listings, Saved Searches, Favorites, and Notification History.

Listings from every marketplace should conform to a shared internal schema to simplify search and filtering.

### 5.4 Listing Data Model
Each listing stores the source marketplace, original URL, asking price, make, model, trim, model year, mileage, seller type, transmission, fuel type, geographic coordinates, photos, description, posting timestamp, last update timestamp, and current listing status.

## 6. Planned Development Timeline

**Week 1 — Project Foundation**
Development begins by establishing the backend infrastructure, database, authentication system, and deployment pipeline. In parallel, the web application is initialized using a modern frontend framework, including routing, authentication flows, responsive layouts, and API integration.

By the end of the first week, developers should have a functioning backend connected to a database and a web frontend capable of communicating with backend services.

**Weeks 2–3 — Listing Aggregation & Backend Infrastructure**
Marketplace connectors are implemented to continuously ingest and normalize listings into a unified data model. Search APIs are developed alongside indexing pipelines, allowing the frontend to retrieve consistent listing data regardless of its source.

**Week 4 — Search Experience**
The web interface introduces universal search, filtering, sorting, and responsive listing cards. The application should provide an excellent experience on both desktop and mobile browsers without requiring separate implementations.

**Week 5 — Listing Details & Favorites**
Dedicated listing pages and user favorites are introduced, allowing users to bookmark vehicles and quickly return to them later.

**Week 6 — Saved Searches & Notifications**
Users can create persistent saved searches that are continuously monitored by the backend. Matching listings generate email notifications and browser push notifications in near real time.

**Weeks 7–8 — Testing, Performance & Launch Preparation**
The final phase focuses on optimizing search performance, improving indexing speed, refining the responsive interface, fixing bugs, and validating browser compatibility. Deployment, monitoring, analytics, and production readiness are completed before public launch.

## 7. MVP Launch Criteria
The MVP will be considered complete once users can access the web application from any modern browser, search aggregated listings, apply filters, browse results, save searches, receive browser or email notifications for matching vehicles, and open the original marketplace listing with a single click.

Future native mobile applications for iOS and Android will reuse the same backend APIs after the web platform has validated product-market fit.

## 8. Future Roadmap
Future releases will focus on building an intelligence layer above the search experience. Planned enhancements include Deal Score, Price History, Duplicate Detection, Days on Market, Similar Listings, VIN decoding, Dealer Reputation, interactive map browsing, market analytics, AI-generated listing summaries, image-based condition analysis, ownership cost forecasting, and negotiation assistance.

These features are intentionally deferred until the core search and notification experience has been validated with real users.
