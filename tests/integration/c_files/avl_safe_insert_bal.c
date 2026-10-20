#include <stdlib.h>

/*
 * Iterative AVL insertion (Knuth, TAOCP vol. 3, 6.2.3, Algorithm A).
 *
 * `root` is a header (sentinel) node: the actual AVL tree hangs from
 * root->right.  This lets rotations change the tree's top node even though
 * the function returns void and takes only one parameter.
 *
 * `key` is left uninitialised on purpose: in the verifier's semantics an
 * uninitialised data variable is a non-deterministic input.
 *
 * bal = height(right) - height(left), always in {-1, 0, 1}.
 *
 * No parent field is needed: while going down we keep
 *   p : the current node (parent of q),
 *   s : the deepest node on the path with bal != 0 (rebalancing point),
 *   t : the parent of s.
 */
struct node {
    int data;
    int bal;
    struct node *left;
    struct node *right;
};

void avl_safe_insert_bal(struct node *root) {
    struct node *t;
    struct node *s;
    struct node *p;
    struct node *q;
    struct node *r;
    struct node *x;
    int key;
    int k;
    int b;
    int a;
    int na;
    int bs;
    int br;
    int bp;

    if (root == NULL)
        return;

    /* empty tree */
    s = root->right;
    if (s == NULL) {
        q = malloc(sizeof(struct node));
        q->data = key;
        q->bal = 0;
        q->left = NULL;
        q->right = NULL;
        root->right = q;
        return;
    }

    /* ---- descent: find the insertion point, tracking t and s ---- */
    t = root;
    q = s;
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
        b = q->bal;
        if (b != 0) {
            t = p;
            s = q;
        }
    }

    /* initialise the new node q (already linked to its parent p) */
    q->data = key;
    q->bal = 0;
    q->left = NULL;
    q->right = NULL;

    /* ---- adjust balance factors on the path s -> q ---- */
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
        k = p->data;
        if (key < k) {
            p->bal = -1;
            p = p->left;
        } else {
            p->bal = 1;
            p = p->right;
        }
    }

    /* ---- balancing act at s ---- */
    na = -a;
    bs = s->bal;
    if (bs == 0) {                      /* tree got taller, still balanced */
        s->bal = a;
        return;
    }
    if (bs == na) {                     /* tree got more balanced */
        s->bal = 0;
        return;
    }

    /* bs == a: s is out of balance, rotate; p becomes the new subtree root */
    br = r->bal;
    if (a == -1) {
        if (br == -1) {                 /* LL: single right rotation */
            p = r;
            x = r->right;
            s->left = x;
            r->right = s;
            s->bal = 0;
            r->bal = 0;
        } else {                        /* LR: double rotation */
            p = r->right;
            x = p->left;
            r->right = x;
            p->left = r;
            x = p->right;
            s->left = x;
            p->right = s;
            bp = p->bal;
            if (bp == -1) {
                s->bal = 1;
                r->bal = 0;
            } else if (bp == 0) {
                s->bal = 0;
                r->bal = 0;
            } else {
                s->bal = 0;
                r->bal = -1;
            }
            p->bal = 0;
        }
    } else {
        if (br == 1) {                  /* RR: single left rotation */
            p = r;
            x = r->left;
            s->right = x;
            r->left = s;
            s->bal = 0;
            r->bal = 0;
        } else {                        /* RL: double rotation */
            p = r->left;
            x = p->right;
            r->left = x;
            p->right = r;
            x = p->left;
            s->right = x;
            p->left = s;
            bp = p->bal;
            if (bp == 1) {
                s->bal = -1;
                r->bal = 0;
            } else if (bp == 0) {
                s->bal = 0;
                r->bal = 0;
            } else {
                s->bal = 0;
                r->bal = 1;
            }
            p->bal = 0;
        }
    }

    /* ---- hang the rebalanced subtree back under t ---- */
    x = t->right;
    if (x == s)
        t->right = p;
    else
        t->left = p;
}
