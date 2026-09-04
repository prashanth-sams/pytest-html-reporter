@ui @smoke
Feature: Reading the heading of a page
  The Gherkin half of screenshot-on-failure. Nothing in the step definitions
  mentions the reporter or a screenshot: the picture is taken because the
  scenario failed while a browser was open, and it is shown against the step
  that failed because that is the step it was taken for.

  Scenario: A wrong heading is photographed on the step that failed
    Given the example page is open
    When the heading is read
    Then it reads "Not the heading"
