#include <stdlib.h>

/*
 * Safe. y = root->left is executed while the lace is in the left child L:
 * it rewinds to the root (frame R, entered from L) and goes straight back
 * down to L (frame Y, Here(y), entered from R and leaving to the root).
 * When z = y->left later re-enters L, the update flags of the new frame
 * count from the root frame Y went up to, not from R: y was set in L itself,
 * so upd_y must be false there.
 */
struct node {
    int data;
    struct node *left;
    struct node *right;
};

void bst_safe_reenter_child(struct node *root) {
    struct node *x;
    struct node *y;
    struct node *w;
    struct node *z;
    int d;

    if (root == NULL)
        return;
    x = root->left;
    if (x == NULL)
        return;
    y = root->left;
    w = root->right;
    if (w == NULL)
        return;
    z = y->left;
    if (z == NULL)
        return;
    d = y->data;
}
