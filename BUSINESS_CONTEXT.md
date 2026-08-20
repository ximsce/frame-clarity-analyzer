# Wedding Glamour Business Context

## Read This First

This document provides the canonical business context for Wedding Glamour's
wedding SaaS business. It is intended to help humans and AI agents understand
the business when planning, designing, implementing, supporting, or evaluating
products and features.

The intended readers are:

- Engineers
- Product managers
- Designers
- Support teams
- Business leaders

Business leaders are the owners of this document. Changes to fundamental facts
about the business require business-leader review and sign-off.

The business context in this document is authoritative. When a proposed feature
or implementation conflicts with it, the conflict must be surfaced and resolved
rather than silently choosing an interpretation. AI agents must ask for
clarification when business context conflicts with downstream feature or
implementation details.

AI agents must not invent missing business or technical policies. This includes
policies concerning privacy, ownership, permissions, retention, moderation,
monetization, or other areas where the brief does not provide an answer. Missing
policies and unresolved conflicts must be raised as questions for the appropriate
business or technical leaders.

This brief covers Wedding Glamour's wedding SaaS business. Project-specific
requirements, implementation details, and temporary technical decisions belong
in the relevant project documentation rather than here.

## Business Identity

Wedding Glamour's mission is to bring joy to wedding couples as they embark on
new journeys together. The intention is for their send-off ceremony to be a
moment of togetherness and celebration.

Wedding couples are often confronted with endless logistics to manage. Wedding
Glamour should serve as a single platform for managing those logistics at a
reasonable price, with professional-quality SaaS features and easy-to-use
interfaces. Professional quality means that features are free from bugs and that
interfaces are intuitive, allowing users to move through their tasks easily and
achieve their intended outcomes without unnecessary stress.

Wedding Glamour's overall aesthetic should be quiet luxury.

Wedding couples or wedding planners pay for Wedding Glamour's services. The
business is primarily direct-to-consumer and primarily serves U.S.-based couples
planning weddings with 100 or more guests.

Wedding Glamour differentiates itself by providing professional-quality SaaS
features that go above and beyond typical wedding SaaS sites, without making
customers feel nickel-and-dimed by separate charges for each service.

Wedding Glamour provides a combination of services that help customers plan
weddings, celebrate them, and preserve wedding memories.

## Product Ecosystem

Wedding Glamour's product ecosystem consists of three equally important areas:

- Event planning
- Guest management
- Memory sharing, allowing guests and other users to share memories

These services are connected through a web portal rather than operating as
unrelated standalone products.

This brief does not distinguish between current, planned, and aspirational
services when describing Wedding Glamour's product ecosystem.

The primary roles in the Wedding Glamour ecosystem are:

- Couples
- Wedding planners
- Guests
- Vendors

## Customers and Users

The primary goal for Wedding Glamour users is to have a single location to plan,
execute, and share memories of their wedding.

Wedding couples are the central customers and have ultimate ownership of the
wedding's event data and shared memories. Couples and wedding planners are the
intended payers for Wedding Glamour's services.

Wedding planners can help manage events and their logistical details on behalf
of the couple.

Guests can RSVP and are core participants in the memory-sharing part of the
product.

Vendors currently have a to-be-determined role. The intention is that
photographers and videographers may also participate in the memory-sharing
feature.

No additional user roles need to be named separately at this time beyond guests
and other users.

## Wedding Domain

A wedding represents a contained span of time focused on the celebration of a
couple joining their lives together, witnessed and shared with friends, family,
and other guests.

The wedding lifecycle consists of:

- Planning
- Event execution, including events leading up to and following the ceremony
- Post-wedding memory sharing and preservation

Wedding event logistics include time, place, transportation, and desired attire.

The initial types of shared memories are:

- Photos
- Videos
- Messages

Additional memory types may be supported in the future.

The couple's ownership of event data and memories includes control over access,
edits, sharing, deletion, and export or download. Individual users may also be
able to edit or delete their own contributions and their presence on the
platform for privacy reasons. The exact rules for those individual controls are
not yet defined.

No domain terms require explicit definitions beyond their ordinary meaning at
this time.

## Media and Video Context

After a wedding, attendees and vendors can find it difficult to share photos and
videos in a single location where all participants can view them, download them,
and order prints. Wedding Glamour's shared-gallery capabilities address this
fragmented experience.

Any registered attendee or vendor can upload photos and videos. Uploads begin as
personal contributions and can be added to the shared gallery content for the
wedding.

Users can view, organize, discover, and share media within the platform. Users
may also download media when they have the additional permission required to do
so.

The intended business outcome of the video feature is to allow attendees to
share particular moments of joy from the wedding.

No business expectations have been defined yet for video quality, processing
time, storage cost, or availability.

## Business Outcomes

Wedding Glamour should help create moments of joy that continue for years to
come, lower the burden of wedding logistics, and reduce stress for the people
using the platform.

The primary business outcome is customer satisfaction. The next business
outcome is industry recognition as the best platform for managing weddings.

Usage of the video feature demonstrates that it is providing value. The specific
behavior or level of usage that should define success remains to be determined.

When business priorities compete, simplicity and privacy should be optimized
over engagement, retention, and the pricing model.

## Business Principles

The following are non-negotiable principles for Wedding Glamour:

- Create joy and togetherness.
- Prefer simplicity and privacy.
- Maintain a quiet-luxury experience.

Quiet luxury guides the entire customer experience, not only the visual design.

Wedding Glamour should also be guided by trust, inclusivity, accessibility,
reliability, and responsiveness to customer feedback.

When principles conflict, sparking joy is foremost, followed by simplicity and
privacy.

## Business Constraints and Policies

Wedding data is private by default. Company administrators should not have
access to wedding data.

Content intended for the shared gallery must be approved unless the couple has
provided explicit permissions for other contributors to add content directly.

Event data and memories should be retained for up to 30 days after the couple
ends payment for Wedding Glamour's services. After that period, the data and
memories should be hard deleted.

Pricing should be commensurate with the cost of maintaining the service and its
related infrastructure. Each wedding will initially have limits on cloud
storage space.

Policies governing downloads, sharing, ordering prints, and individual
contributor controls have not yet been defined. No moderation, reporting, or
additional consent policy has been defined at this time.

## Canonical Terminology

No domain terms require explicit definitions beyond their ordinary meaning at
this time.

## Confirmed Facts

This section is an index of the authoritative facts in this brief. It is not a
duplicate of the sections above.

Unless explicitly qualified, statements in this brief are confirmed business
facts. Statements using terms such as "should," "intended," "may," "initially,"
or "TBD" describe business intent, a possible future direction, or an unresolved
question rather than a settled fact.

The authoritative facts are organized in these sections:

- **Read This First:** The brief's authority, audience, ownership, and guidance
  for AI agents
- **Business Identity:** Wedding Glamour's business, mission, market, positioning,
  and customer problem
- **Product Ecosystem:** The equally important product areas, web portal, and
  primary roles
- **Customers and Users:** User goals, role purposes, intended payers, and data
  ownership
- **Wedding Domain:** The meaning and lifecycle of a wedding, logistics, and
  memory types
- **Media and Video Context:** The shared-gallery problem, contributor model, and
  supported media activities
- **Business Outcomes:** Desired customer outcomes and business priorities
- **Business Principles:** Non-negotiable principles and conflict priorities
- **Business Constraints and Policies:** Confirmed privacy, approval, retention,
  deletion, storage, and pricing policies

## Assumptions and Open Questions

The following items are intentionally unresolved or provisional:

- The specific role and capabilities of vendors in the product
- Whether additional memory types beyond photos, videos, and messages will be
  supported
- The exact controls individual contributors have over their own contributions
  and presence on the platform
- Permissions for downloading, sharing, and ordering prints
- Moderation, reporting, and additional consent policies
- The user behavior or level of usage that defines success for the video feature
- Business expectations for video quality, processing time, storage cost, and
  availability
- The initial cloud-storage limits for each wedding

Projects and AI agents must not resolve these items by assumption. Questions
that depend on them should be raised with the appropriate business or technical
leaders.

## Maintenance

The Wedding Glamour Executive Team owns this document and is responsible for
reviewing and updating it quarterly.

Business-leader sign-off must be recorded through pull-request approval. This
repository is the canonical source for the brief for now.

The distinction between edits that require executive-team sign-off and minor
editorial changes that do not is still to be determined.
