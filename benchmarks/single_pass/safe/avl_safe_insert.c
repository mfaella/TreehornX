#include <stdio.h>
#include <stdlib.h>

/* ============================================================
 * The structure and the insertion function below are IDENTICAL
 * to avl_safe_insert.c. The ONLY change is the 'null' variable,
 * which here is really initialised to NULL so the code can run
 * under a normal C compiler (the C-subset uses 'null' as a magic
 * identifier denoting the null pointer).
 * ============================================================ */

struct Node {
    int data;
    int height;
    struct Node *left;
    struct Node *right;
    struct Node *parent;
};

void avl_safe_insert(struct Node* root, int value) {
    struct Node *null;          /* <-- only difference vs. the deliverable */
    struct Node *current;
    struct Node *parent;
    struct Node *newNode;
    struct Node *node;
    struct Node *up;
    struct Node *child;
    struct Node *p;
    struct Node *g;
    struct Node *x;
    struct Node *y;
    struct Node *t2;
    int tmp;
    int hl;
    int hr;
    int h;
    int chl;
    int chr;
    int more;

    // ---- 1. binary-search-tree descent to the insertion point ----
    parent = root;
    current = root->left;
    while (current) {
        parent = current;
        tmp = current->data;
        if (value < tmp) {
            current = current->left;
        } else {
            current = current->right;
        }
    }

    // 2. create the new leaf and attach it
    newNode = malloc(sizeof(struct Node));
    newNode->data = value;
    newNode->height = 1;
    newNode->left = null;
    newNode->right = null;
    newNode->parent = parent;
    if (parent == root) {
        root->left = newNode;
    } else {
        tmp = parent->data;
        if (value < tmp) {
            parent->left = newNode;
        } else {
            parent->right = newNode;
        }
    }

    // 3. walk back up the ancestors, fixing heights and rotating
    node = parent;
    more = 1;
    while (more == 1) {
        if (node == root) {
            more = 0;
        } else {
            up = node->parent;

            if (node->left == null) { hl = 0; } else { hl = node->left->height; }
            if (node->right == null) { hr = 0; } else { hr = node->right->height; }
            if (hl < hr) { h = hr; } else { h = hl; }
            node->height = h + 1;

            if (hr + 1 < hl) {
                child = node->left;
                if (child->left == null) { chl = 0; } else { chl = child->left->height; }
                if (child->right == null) { chr = 0; } else { chr = child->right->height; }

                if (chl < chr) {
                    p = child;
                    y = p->right;
                    t2 = y->left;
                    g = p->parent;
                    y->parent = g;
                    if (g->left == p) { g->left = y; } else { g->right = y; }
                    y->left = p;
                    p->parent = y;
                    p->right = t2;
                    if (t2 == null) { } else { t2->parent = p; }
                    if (p->left == null) { hl = 0; } else { hl = p->left->height; }
                    if (p->right == null) { hr = 0; } else { hr = p->right->height; }
                    if (hl < hr) { h = hr; } else { h = hl; }
                    p->height = h + 1;
                    if (y->left == null) { hl = 0; } else { hl = y->left->height; }
                    if (y->right == null) { hr = 0; } else { hr = y->right->height; }
                    if (hl < hr) { h = hr; } else { h = hl; }
                    y->height = h + 1;
                }

                p = node;
                x = p->left;
                t2 = x->right;
                g = p->parent;
                x->parent = g;
                if (g->left == p) { g->left = x; } else { g->right = x; }
                x->right = p;
                p->parent = x;
                p->left = t2;
                if (t2 == null) { } else { t2->parent = p; }
                if (p->left == null) { hl = 0; } else { hl = p->left->height; }
                if (p->right == null) { hr = 0; } else { hr = p->right->height; }
                if (hl < hr) { h = hr; } else { h = hl; }
                p->height = h + 1;
                if (x->left == null) { hl = 0; } else { hl = x->left->height; }
                if (x->right == null) { hr = 0; } else { hr = x->right->height; }
                if (hl < hr) { h = hr; } else { h = hl; }
                x->height = h + 1;
            } else {
                if (hl + 1 < hr) {
                    child = node->right;
                    if (child->left == null) { chl = 0; } else { chl = child->left->height; }
                    if (child->right == null) { chr = 0; } else { chr = child->right->height; }

                    if (chr < chl) {
                        p = child;
                        x = p->left;
                        t2 = x->right;
                        g = p->parent;
                        x->parent = g;
                        if (g->left == p) { g->left = x; } else { g->right = x; }
                        x->right = p;
                        p->parent = x;
                        p->left = t2;
                        if (t2 == null) { } else { t2->parent = p; }
                        if (p->left == null) { hl = 0; } else { hl = p->left->height; }
                        if (p->right == null) { hr = 0; } else { hr = p->right->height; }
                        if (hl < hr) { h = hr; } else { h = hl; }
                        p->height = h + 1;
                        if (x->left == null) { hl = 0; } else { hl = x->left->height; }
                        if (x->right == null) { hr = 0; } else { hr = x->right->height; }
                        if (hl < hr) { h = hr; } else { h = hl; }
                        x->height = h + 1;
                    }

                    p = node;
                    y = p->right;
                    t2 = y->left;
                    g = p->parent;
                    y->parent = g;
                    if (g->left == p) { g->left = y; } else { g->right = y; }
                    y->left = p;
                    p->parent = y;
                    p->right = t2;
                    if (t2 == null) { } else { t2->parent = p; }
                    if (p->left == null) { hl = 0; } else { hl = p->left->height; }
                    if (p->right == null) { hr = 0; } else { hr = p->right->height; }
                    if (hl < hr) { h = hr; } else { h = hl; }
                    p->height = h + 1;
                    if (y->left == null) { hl = 0; } else { hl = y->left->height; }
                    if (y->right == null) { hr = 0; } else { hr = y->right->height; }
                    if (hl < hr) { h = hr; } else { h = hl; }
                    y->height = h + 1;
                }
            }

            node = up;
        }
    }
}
