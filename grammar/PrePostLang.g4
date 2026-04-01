grammar PrePostLang;

// -----------------------------------------
// PARSER RULES
// -----------------------------------------

program: statement* EOF;

statement
    : varDecl SEMI
    | enumDecl SEMI
    | letDecl SEMI
    | bExpr SEMI
    ;

varDecl: VAR id;

enumDecl: ENUM id;

letDecl: letDeclNoParam | letDeclWithParams;

letDeclNoParam: LET id ARROW expr;

letDeclWithParams: LET id LPAREN id (COMMA id)* RPAREN ARROW expr;

expr
    : bExpr
    | aExpr
    ;

bExpr: //boolean expresions
    | orExpr
    | bIteExpr
    | bItExpr
    ;

orExpr: andExpr (OR orExpr)?;

andExpr: notExpr (AND andExpr)?;

bCmpExpr: notExpr (IFF notExpr);

notExpr: NOT? bTerm;

bTerm
    : true
    | false
    | atom
    | bParExpr
    | isRoot
    | isNil
    | isLeaf
    | application
    | aCmpExpr
    ;

true: TRUE;

false: FALSE;

atom
    : id
    | field
    | parentQ
    | fieldQ
    | nodeQ
    ;

id: ID | VAR | LET;

field: FIELD;

parentQ: PARENT_Q;

fieldQ: FIELD_Q;

nodeQ: NODE_Q;

bParExpr: LPAREN bExpr RPAREN;

isNil: ISNIL LPAREN nodeAtom RPAREN;

isRoot: ISROOT LPAREN nodeAtom RPAREN;

isLeaf: ISLEAF LPAREN nodeAtom RPAREN;

nodeAtom
    : parent
    | field
    | id
    ;

parent: PARENT;

application: id LPAREN arg (COMMA arg)* RPAREN;

arg
    : expr
    | nodeAtom
    ;

aCmpExpr: aExpr op=(EQ|GT|GE|LT|LE) aExpr;

bIteExpr: IF bExpr THEN bExpr ELSE bExpr;

bItExpr: IF bExpr THEN bExpr;

aExpr: aSumExpr | aIteExpr; //arithmetic expression

aIteExpr: IF bExpr THEN aExpr ELSE aExpr;

aSumExpr: aMulExpr ((PLUS|MINUS) aSumExpr)?;

aMulExpr: aNegExpr ((MUL|DIV) aMulExpr)?;

aNegExpr: MINUS? aTerm;

aTerm
    : nat
    | atom
    | enumVariant
    | aParExpr
    ;

nat: NATURAL;

enumVariant: ENUM_VARIANT;

aParExpr: LPAREN aExpr RPAREN;

// -----------------------------------------
// LEXER RULES
// -----------------------------------------

// Keywords
LET: 'let';
ISNIL: '$isnil';
ISROOT: '$isroot';
ISLEAF: '$isleaf';
AND: 'and';
OR: 'or';
NOT: 'not';
IF: 'if';
THEN: 'then';
ELSE: 'else';
VAR: 'var';
ENUM: 'enum';
ENUM_VARIANT: [a-zA-Z_][a-zA-Z0-9_]*'::'[a-zA-Z_][a-zA-Z0-9_]*;

// Default Variables & Fields
PARENT: '#';
PARENT_Q: '#:'[a-zA-Z_][a-zA-Z0-9_]*;
FIELD: '#'[a-zA-Z_][a-zA-Z0-9_]*;
FIELD_Q: '#'[a-zA-Z_][a-zA-Z0-9_]*':'[a-zA-Z_][a-zA-Z0-9_]*;
NODE_Q: [a-zA-Z_][a-zA-Z0-9_]*':'[a-zA-Z_][a-zA-Z0-9_]*;

// Operators & Punctuation
IFF: '<>';
PLUS: '+';
MINUS: '-';
MUL: '*';
DIV: '/';
EQ: '=';
GT: '>';
LT: '<';
GE: '>=';
LE: '<=';
LPAREN: '(';
RPAREN: ')';
COMMA: ',';
SEMI: ';';
ARROW: '=>';

// Identifiers and Literals
ID: [a-zA-Z_][a-zA-Z0-9_]*;
NATURAL: [0-9]+;
FALSE: 'false';
TRUE: 'true';

// Whitespace (Ignored)
WS: [ \t\r\n]+ -> skip;
BLOCK_COMMENT : '(*' .*? '*)' -> skip;
