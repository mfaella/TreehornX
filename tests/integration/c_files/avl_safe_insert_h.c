#include <stdlib.h>

/*
 * Iterative AVL insertion (Knuth, TAOCP vol. 3, 6.2.3, Algorithm A),
 * adapted to store the HEIGHT of each subtree instead of its balance factor.
 * NO sentinel, no key movement:
 * `root` is the top node of the tree, and the final value of the variable
 * `root` is the top node of the resulting tree.
 *
 * Rotations relink nodes; keys never move between nodes.  When the
 * rotation happens at the top of the tree, the new top node is assigned to
 * `root`.  An empty tree (root == NULL) becomes a single node assigned to
 * `root`.
 *
 * `key` is left uninitialised on purpose: in the verifier's semantics an
 * uninitialised data variable is a non-deterministic input.
 *
 * height(NULL) = 0, height(leaf) = 1,
 * height(n) = 1 + max(height(n->left), height(n->right)),
 * and |height(right) - height(left)| <= 1 at every node.
 *
 * No parent field is needed: while going down we keep
 *   p : the current node (parent of q),
 *   s : the deepest node on the path whose children have different
 *       heights (rebalancing point),
 *   t : the parent of s (NULL while s is the top node).
 *
 * Why only the path s -> q needs fixing: every node strictly below s on the
 * path had equal-height children, so its height grows by exactly 1.  At s
 * either the height grows (s was balanced, which only happens when s is the
 * top), stays the same (the insertion went to the shorter side), or a
 * rotation restores s's original height.  Nodes above s never change.
 */
struct node {
    int data;
    int height;
    struct node *left;
    struct node *right;
};

void avl_insert(struct node *root) {
    struct node *t;
    struct node *s;
    struct node *p;
    struct node *q;
    struct node *r;
    struct node *x;
    int key;
    int k;
    int a;
    int hl;
    int hr;
    int h;
    int h1;
    int d;

    /* empty tree: the new node becomes the top */
    if (root == NULL) {
        q = malloc(sizeof(struct node));
        q->data = key;
        q->height = 1;
        q->left = NULL;
        q->right = NULL;
        root = q;
        return;
    }

    /* ---- descent: find the insertion point, tracking t and s ---- */
    t = NULL;
    s = root;
    q = root;
    while (q != NULL) {
        p = q;
        k = p->data;
        if (key < k) {
            q = p->left;
            if (q == NULL) {
                q = malloc(sizeof(struct node));
                p->left = q;
                break;
            }
        } else if (key > k) {
            q = p->right;
            if (q == NULL) {
                q = malloc(sizeof(struct node));
                p->right = q;
                break;
            }
        } else {
            return;                     /* key already present */
        }
        /* is q unbalanced (children of different heights)? */
        x = q->left;
        if (x == NULL)
            hl = 0;
        else
            hl = x->height;
        x = q->right;
        if (x == NULL)
            hr = 0;
        else
            hr = x->height;
        if (hl != hr) {
            t = p;
            s = q;
        }
    }

    /* initialise the new node q (already linked to its parent p) */
    q->data = key;
    q->height = 1;
    q->left = NULL;
    q->right = NULL;

    /* ---- adjust heights on the path strictly between s and q ---- */
    k = s->data;
    if (key < k) {
        a = -1;
        r = s->left;
    } else {
        a = 1;
        r = s->right;
    }
    p = r;
    while (p != q) {
        h = p->height;
        h1 = h + 1;
        p->height = h1;                 /* was balanced, so grows by 1 */
        k = p->data;
        if (key < k)
            p = p->left;
        else
            p = p->right;
    }

    /* ---- balancing act at s ---- */
    x = s->left;
    if (x == NULL)
        hl = 0;
    else
        hl = x->height;
    x = s->right;
    if (x == NULL)
        hr = 0;
    else
        hr = x->height;
    d = hr - hl;
    if (d >= -1 && d <= 1) {            /* still balanced: just refresh */
        if (hl > hr)
            h = hl;
        else
            h = hr;
        h1 = h + 1;
        s->height = h1;
        return;
    }

    /*
     * |d| == 2 (d == 2*a): s is out of balance, rotate; p becomes the new
     * subtree root.  s->height still holds the old height H of the subtree,
     * and the rebalanced subtree must have height H again:
     *   single rotation: s -> H-1, r stays H
     *   double rotation: s -> H-1, r -> H-1, p -> H
     */
    k = r->data;
    if (a == -1) {
        if (key < k) {                  /* LL: single right rotation */
            p = r;
            x = r->right;
            s->left = x;
            r->right = s;
            h = s->height;
            h1 = h - 1;
            s->height = h1;
        } else {                        /* LR: double rotation */
            p = r->right;
            x = p->left;
            r->right = x;
            p->left = r;
            x = p->right;
            s->left = x;
            p->right = s;
            h = s->height;
            h1 = h - 1;
            s->height = h1;
            r->height = h1;
            p->height = h;
        }
    } else {
        if (key > k) {                  /* RR: single left rotation */
            p = r;
            x = r->left;
            s->right = x;
            r->left = s;
            h = s->height;
            h1 = h - 1;
            s->height = h1;
        } else {                        /* RL: double rotation */
            p = r->left;
            x = p->right;
            r->left = x;
            p->right = r;
            x = p->left;
            s->right = x;
            p->left = s;
            h = s->height;
            h1 = h - 1;
            s->height = h1;
            r->height = h1;
            p->height = h;
        }
    }

    /* ---- hang the rebalanced subtree back under t, or make it the top ---- */
    if (s == root) {
        root = p;                       /* p is the new top of the tree */
    } else {
        x = t->right;
        if (x == s)
            t->right = p;
        else
            t->left = p;
    }
}
