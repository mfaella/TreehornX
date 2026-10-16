struct Node {
    int data;
    int height;
    struct Node *left;
    struct Node *right;
};

/*
 * Iterative AVL insertion without parent pointers (Knuth, TAOCP vol. 3, 6.2.3, Algorithm A), with heights
 * instead of balance factors: a missing child has height 0 and a leaf height 1.
 *
 * 1. Search the key, remembering s, the deepest node on the path whose subtrees have different heights,
 *    and its parent t. Every node below s on the path has subtrees of equal height.
 * 2. Attach the new leaf.
 * 3. Walk again from s to the new leaf: the nodes strictly in between grow by one.
 * 4. Update the height of s, or rebalance it with a single or double rotation, and hang the new subtree
 *    under t.
 */
void avl_safe_insert(struct Node *root) {
    struct Node *t;
    struct Node *s;
    struct Node *p;
    struct Node *q;
    struct Node *l;
    struct Node *r;
    struct Node *a;
    struct Node *b;
    struct Node *c;
    struct Node *n;
    struct Node *sub;
    int key;
    int pkey;
    int skey;
    int akey;
    int tkey;
    int hl;
    int hr;
    int h;

    if (!root) {
        n = malloc(sizeof(struct Node));
        n->data = key;
        n->height = 1;
        root = n;
        return;
    }

    /* 1. search */
    s = root;
    q = root;
    while (q) {
        p = q;
        pkey = p->data;
        if (key == pkey) {
            return;
        }
        if (key < pkey) {
            q = p->left;
        } else {
            q = p->right;
        }
        if (q) {
            l = q->left;
            if (l) {
                hl = l->height;
            } else {
                hl = 0;
            }
            r = q->right;
            if (r) {
                hr = r->height;
            } else {
                hr = 0;
            }
            if (hl != hr) {
                t = p;
                s = q;
            }
        }
    }

    /* 2. insert the new leaf under p */
    n = malloc(sizeof(struct Node));
    n->data = key;
    n->height = 1;
    if (key < pkey) {
        p->left = n;
    } else {
        p->right = n;
    }

    /* 3. the nodes strictly between s and the new leaf grow by one */
    skey = s->data;
    if (key < skey) {
        a = s->left;
    } else {
        a = s->right;
    }
    q = a;
    while (q != n) {
        h = q->height;
        h = h + 1;
        q->height = h;
        pkey = q->data;
        if (key < pkey) {
            q = q->left;
        } else {
            q = q->right;
        }
    }

    /* 4. height of s, or rebalancing */
    l = s->left;
    if (l) {
        hl = l->height;
    } else {
        hl = 0;
    }
    r = s->right;
    if (r) {
        hr = r->height;
    } else {
        hr = 0;
    }
    h = hl - hr;
    if (h >= -1 && h <= 1) {
        if (hl > hr) {
            h = hl + 1;
            s->height = h;
        } else {
            h = hr + 1;
            s->height = h;
        }
        return;
    }

    akey = a->data;
    if (key < skey) {
        if (key < akey) {
            /* left-left: rotate s to the right */
            b = a->right;
            a->right = s;
            s->left = b;
            sub = a;
        } else {
            /* left-right: rotate a to the left, then s to the right */
            b = a->right;
            c = b->left;
            a->right = c;
            c = b->right;
            s->left = c;
            b->left = a;
            b->right = s;
            sub = b;
        }
    } else {
        if (key > akey) {
            /* right-right: rotate s to the left */
            b = a->left;
            a->left = s;
            s->right = b;
            sub = a;
        } else {
            /* right-left: rotate a to the right, then s to the left */
            b = a->left;
            c = b->right;
            a->left = c;
            c = b->left;
            s->right = c;
            b->right = a;
            b->left = s;
            sub = b;
        }
    }

    /* heights of the rotated nodes, bottom-up: s, a (if below sub), sub */
    l = s->left;
    if (l) {
        hl = l->height;
    } else {
        hl = 0;
    }
    r = s->right;
    if (r) {
        hr = r->height;
    } else {
        hr = 0;
    }
    if (hl > hr) {
        h = hl + 1;
        s->height = h;
    } else {
        h = hr + 1;
        s->height = h;
    }

    if (sub != a) {
        l = a->left;
        if (l) {
            hl = l->height;
        } else {
            hl = 0;
        }
        r = a->right;
        if (r) {
            hr = r->height;
        } else {
            hr = 0;
        }
        if (hl > hr) {
            h = hl + 1;
            a->height = h;
        } else {
            h = hr + 1;
            a->height = h;
        }
    }

    l = sub->left;
    if (l) {
        hl = l->height;
    } else {
        hl = 0;
    }
    r = sub->right;
    if (r) {
        hr = r->height;
    } else {
        hr = 0;
    }
    if (hl > hr) {
        h = hl + 1;
        sub->height = h;
    } else {
        h = hr + 1;
        sub->height = h;
    }

    /* hang the rebalanced subtree where s was */
    if (!t) {
        root = sub;
    } else {
        tkey = t->data;
        if (key < tkey) {
            t->left = sub;
        } else {
            t->right = sub;
        }
    }
}
