## PrePostLang
This is the language to describe pre and post condition of a generic program that manipulates tree data structures.
It can describe logic formulas to ensure properties at the begin and at the end of a program. To ensure enviroment 
consistency (types and variables) between a PrePostLang script and the program the enviroment must be imported into the script.
To import a variable type
```
var <var-name>
```
If no variable with such name exists in the program scope it raises an error.
The same is applied to enumerations.
```
enum <enum-type-name>
```
This design choice has the goal to avoid name shadowing.

## Mapping to ir expression
### let declaration
It is comparable to a macro in C, it defines a portion of code that gets expanded when called. Type inference on parameteres
is computed as for other expressions. A parameter name, can not shadow a global scope variable.

### Operator mapping
All the expressions can trivially be mapped to ir expressions, but boolean if-then and if-then-else, integer if-then-else, iff and states values.
- boolean if-then: let the expression be if <cond> then <consequence> a PrePostLang expression, it gets mapped to (or (not cond) consequence) 
- boolean if-then-else: let the expression be if <cond> then <true-cons> else <false-cons> a PrePostLang expression, it gets mapped to (and (or (not cond) true-cons) (or cond true-cons))
- iff: let <left> <> <right> be a PrePostLang expression it gets mapped to (= left right)
- integer if-then-else: it is trickier because it depends on the context
--- <expr> <op> (if <cond> then <true-expr> else <false-expr>) gets mapped to (and (or (not cond) (op expr true-expr)) (or cond (op expr false-expr)))
--- (if <cond1> then <true-expr1> else <false-expr1>) <op> (if <cond2> then <true-expr2> else <false-expr2>) follows the same procedure for the previous case but the conditions we evaluate are the corss product of conditions in both if-the-else expression; it gets mapped to
(and  
(or (not (and cond1 cond2)) (op true-expr1 true-expr2))               // (or (not cond1) (not cond2) (op true-expr1 true-expr2))
(or (not (and (not cond1) cond2)) (op false-expr1 true-expr2))        // (or cond1 (not cond2) (op false-expr1 true-expr2))
(or (not (and cond1 (not cond2))) (op true-expr1 false-expr2))        // (or (not cond1) cond2 (op true-expr1 false-expr2))
(or (not (and (not cond1) (not cond2))) (op false-expr1 false-expr2)) // (or cond1 cond2 (op false-expr1 false-expr2))
)
- states values (#:q, #child:q, n:q): these expression are managed as simple variables named respectively $q and $child$q, n$q.

### example of pre on rbtree
let red(n) => n:color = Color::Red
let black(n) => n:color = Color::Black

(* colors rules *)
if $isroot(#) then black(#);
if red(#) then black(#left) and black(#right);
if $isnil(#) then black(#);

(* black height rules *)
let incbh => if black(#) then 1 else 0;
if $isnil(#) then #:bh = 0
else #:bh = #left:bh + incbh and #left:bh = #right:bh;
#:color = #color;

(* bst rules *)
if not $isnil(#left) then #left:max <= #value;
if not $isnil(#right) then #right:min > #value;
#:min = if $isnil(#left) then #value else #left:min;
#:max = if $isnil(#right) then #value else #right:max;
