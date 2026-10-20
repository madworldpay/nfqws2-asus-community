module.exports = {
  plugins: ['stylelint-use-logical-spec'],
  rules: {
    'no-descending-specificity': null,
    'selector-class-pattern': '^[a-z][a-zA-Z0-9_]+$',
    'declaration-block-no-redundant-longhand-properties': [
      true,
      {
        ignoreShorthands: ['flex', 'place-content', 'place-items'],
      },
    ],
    'selector-pseudo-class-no-unknown': [
      true,
      {
        ignorePseudoClasses: ['global'],
      },
    ],
    'media-feature-range-notation': null,
    'liberty/use-logical-spec': [
      'always',
      {
        except: [/width|height|top|bottom/i],
      },
    ],
  },
  overrides: [
    {
      files: ['**/*.css'],
      extends: ['stylelint-config-standard'],
    },
    {
      files: ['**/*.scss'],
      extends: ['stylelint-config-standard-scss'],
      customSyntax: 'postcss-scss',
    },
  ],
};
