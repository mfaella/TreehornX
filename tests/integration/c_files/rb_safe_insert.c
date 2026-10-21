#include <stdlib.h>
#include <stdbool.h>

/*
 * Iterative red-black tree insertion, NO sentinel, no key movement:
 * `root` is the top node of the tree, and the final value of the variable
 * `root` is the top node of the resulting tree.
 *
 * Rotations relink nodes; keys never move between nodes.  When the final
 * rotation (case 3) happens at the top of the tree, the new top node is
 * assigned to `root`.  An empty tree (root == NULL) becomes a single black
 * node assigned to `root`.
 *
 * Preconditions:
 *   - the tree is a valid red-black tree (in particular root is black),
 *   - nothing is assumed about the `parent` fields: the descent assigns
 *     q->parent for every node q it visits below root, and the fix-up only
 *     reads parent fields of those nodes.  The parent field of the (old or
 *     new) top node is never read.
 *
 * `key` is left uninitialised on purpose: in the verifier's semantics an
 * uninitialised data variable is a non-deterministic input.
 *
 * red == true : red node,  red == false : black node  (NULL = black)
 */
struct node {
    int data;
    bool red;
    struct node *left;
    struct node *right;
    struct node *parent;
};

void rb_insert(struct node *root) {
    struct node *p;
    struct node *q;
    struct node *x;
    struct node *g;
    struct node *u;
    struct node *y;
    struct node *z;
    struct node *w;
    int key;
    int k;
    bool c;
    bool uc;

    /* empty tree: the new node becomes the (black) top */
    if (root == NULL) {
        q = malloc(sizeof(struct node));
        q->data = key;
        q->red = false;
        q->left = NULL;
        q->right = NULL;
        root = q;
        return;
    }

    /* ---- descent: ordinary BST insertion, parent set on the way down ---- */
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
            return;                 /* key already present */
        }
        q->parent = p;              /* visited child: assign its parent */
    }
    q->data = key;
    q->red = true;                  /* new nodes are red */
    q->left = NULL;
    q->right = NULL;
    q->parent = p;

    /* ---- fix-up: repair red-red violations going up ---- */
    x = q;
    while (x != root) {
        p = x->parent;
        c = p->red;
        if (!c)
            break;                  /* parent black: done */
        if (p == root)
            break;                  /* red top: fixed by the final recolour */
        g = p->parent;              /* p red and not the top: g is a real node */
        y = g->left;
        if (y == p) {
            /* ======== p is a left child; uncle is g->right ======== */
            u = g->right;
            uc = false;
            if (u != NULL)
                uc = u->red;
            if (uc) {
                /* case 1: red uncle -> recolour, continue from g */
                p->red = false;
                u->red = false;
                g->red = true;
                x = g;
            } else {
                y = p->right;
                if (x == y) {
                    /* case 2 (LR): rotate left at p, then x/p swap roles */
                    y = x->left;
                    p->right = y;
                    x->parent = g;
                    g->left = x;
                    x->left = p;
                    p->parent = x;
                    y = x;
                    x = p;
                    p = y;
                }
                /* case 3 (LL): recolour and rotate right at g */
                p->red = false;
                g->red = true;
                y = p->right;
                g->left = y;
                if (g == root) {
                    root = p;           /* p is the new top of the tree */
                } else {
                    z = g->parent;
                    p->parent = z;
                    w = z->left;
                    if (w == g)
                        z->left = p;
                    else
                        z->right = p;
                }
                p->right = g;
                g->parent = p;
                break;                  /* p is black now: done */
            }
        } else {
            /* ======== p is a right child; uncle is g->left ======== */
            u = g->left;
            uc = false;
            if (u != NULL)
                uc = u->red;
            if (uc) {
                /* case 1: red uncle -> recolour, continue from g */
                p->red = false;
                u->red = false;
                g->red = true;
                x = g;
            } else {
                y = p->left;
                if (x == y) {
                    /* case 2 (RL): rotate right at p, then x/p swap roles */
                    y = x->right;
                    p->left = y;
                    x->parent = g;
                    g->right = x;
                    x->right = p;
                    p->parent = x;
                    y = x;
                    x = p;
                    p = y;
                }
                /* case 3 (RR): recolour and rotate left at g */
                p->red = false;
                g->red = true;
                y = p->left;
                g->right = y;
                if (g == root) {
                    root = p;           /* p is the new top of the tree */
                } else {
                    z = g->parent;
                    p->parent = z;
                    w = z->left;
                    if (w == g)
                        z->left = p;
                    else
                        z->right = p;
                }
                p->left = g;
                g->parent = p;
                break;                  /* p is black now: done */
            }
        }
    }

    /* the top of the tree is always black */
    root->red = false;
}
