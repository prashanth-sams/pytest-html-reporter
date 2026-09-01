@smoke @checkout
Feature: Checking out a basket
  The Gherkin half of the Test Steps tab. Nothing in the step definitions
  mentions the reporter - a scenario is already a list of named steps, so its
  Given / When / Then arrive on the tab on their own.

  Scenario Outline: A shopper buys <count> of an item
    Given a logged in shopper
    When they add <count> of "A-12" to the basket
    Then the basket holds <count> items

    Examples:
      | count |
      | 1     |
      | 3     |

  @declined
  Scenario: A declined card names the step that failed
    Given a logged in shopper
    When they add 1 of "DECLINE" to the basket
    And they check out
    Then the basket holds 0 items
